"""Local Flask UX for the JobSearch project.

Single-user, localhost-only. Zero LLM calls — orchestrates scripts only.
The tailoring step itself happens inside Claude Code; the UI surfaces the
exact slash command to run.

Usage:
    JOBSEARCH_ROOT=/path/to/JobSearch \
        .venv/bin/python -m flask --app ui.app run --port 5050
or use the helper:
    .venv/bin/python ui/app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
import markdown as md
from flask import (
    Flask, abort, redirect, render_template, request, send_file, url_for, flash
)
from werkzeug.utils import secure_filename

# Allow `import build_resume` etc.
_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parent
sys.path.insert(0, str(_DEFAULT_ROOT / "scripts"))

from build_resume import build_general, build_job  # noqa: E402
from new_job import make_job_folder, write_job_yaml  # noqa: E402
from capture_job import capture  # noqa: E402
from lint_resume import LintError  # noqa: E402
from status import (  # noqa: E402
    derive_state, set_explicit_state, EXPLICIT_STATES, APPLIED_STATES, progress,
)
from render import render_html  # noqa: E402
from yaml_path import set_by_path  # noqa: E402


def create_app(root: Path | None = None) -> Flask:
    root = Path(root or os.environ.get("JOBSEARCH_ROOT", _DEFAULT_ROOT)).resolve()
    # The scripts also read JOBSEARCH_ROOT to find the kitchen sink / jobs dir.
    os.environ["JOBSEARCH_ROOT"] = str(root)

    app = Flask(__name__, template_folder=str(_HERE / "templates"),
                static_folder=str(_HERE / "static"))
    app.config["SECRET_KEY"] = "jobsearch-local-dev"
    app.config["JOBSEARCH_ROOT"] = root

    # -------- helpers --------

    def jobs_dir() -> Path:
        return root / "jobs"

    def job_path(slug: str) -> Path:
        p = (jobs_dir() / slug).resolve()
        if jobs_dir().resolve() not in p.parents and p != jobs_dir().resolve():
            abort(404)  # path traversal guard
        if not p.is_dir():
            abort(404)
        return p

    def list_jobs() -> list[dict]:
        if not jobs_dir().exists():
            return []
        out = []
        for d in sorted(jobs_dir().iterdir(), reverse=True):
            if not d.is_dir():
                continue
            meta = {}
            yml = d / "job.yaml"
            if yml.exists():
                try:
                    meta = yaml.safe_load(yml.read_text()) or {}
                except yaml.YAMLError:
                    meta = {}
            st = derive_state(d)
            out.append({
                "slug": d.name,
                "company": meta.get("company") or "",
                "role": meta.get("role") or "",
                "url": meta.get("url") or "",
                "state": st.state,
                "is_explicit": st.is_explicit,
                "next_step": st.next_step,
                "date_added": meta.get("date_added") or "",
                "has_resume": (d / "resume.docx").exists(),
                "has_screenshot": (d / "job-screenshot.png").exists(),
                "has_tailored": (d / "resume-source.yaml").exists(),
                "capture_complete": st.capture_complete,
                "capture_missing": list(st.capture_missing),
                "applied": st.state in APPLIED_STATES,
            })
        return out

    def read_text(p: Path) -> str:
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def md_to_html(text: str) -> str:
        return md.markdown(text or "", extensions=["fenced_code", "tables"])

    def read_questions(p: Path) -> dict:
        qf = p / "background-questions.yaml"
        if not qf.exists():
            return {}
        try:
            return yaml.safe_load(qf.read_text()) or {}
        except yaml.YAMLError:
            return {}

    def _profile_for(slug: str | None) -> dict:
        """The same data the renderer would consume for this view."""
        import yaml as _yaml
        ks = root / "kitchen-sink" / "profile.yaml"
        profile = _yaml.safe_load(ks.read_text()) if ks.exists() else {}
        if slug is None:
            return profile or {}
        folder = root / "jobs" / slug
        tailored = folder / "resume-source.yaml"
        if tailored.exists():
            data = _yaml.safe_load(tailored.read_text())
            if data:
                return data
        return profile or {}

    def _lint_findings(slug: str | None) -> list:
        from lint_resume import lint
        try:
            return lint(_profile_for(slug))
        except Exception:
            return []

    # -------- routes --------

    @app.route("/")
    def index():
        general_docx = root / "general-resume" / "general-resume.docx"
        return render_template(
            "index.html",
            jobs=list_jobs(),
            general_built=general_docx.exists(),
            general_mtime=general_docx.stat().st_mtime if general_docx.exists() else None,
        )

    @app.route("/jobs", methods=["POST"])
    def create_job():
        url = (request.form.get("url") or "").strip()
        company = (request.form.get("company") or "").strip() or None
        role = (request.form.get("role") or "").strip() or None
        capture_now = request.form.get("capture") in ("on", "true", "1")

        if not url:
            flash("URL is required.", "error")
            return redirect(url_for("index"))

        folder = make_job_folder(url, company, role, root=root)
        write_job_yaml(folder, url, company, role)

        if capture_now:
            try:
                result = capture(url, folder)
                if result.get("complete"):
                    flash(f"Captured the posting via {result['via']} "
                          f"({result['words']} words).", "info")
                elif result["status"] == "needs_manual_paste":
                    flash(f"Capture failed (thin content). Run "
                          f"/capture-job jobs/{folder.name} in Claude Code to extract "
                          f"from the screenshot, or paste it manually.", "warn")
                else:
                    flash(f"Captured via {result['via']} but it looks incomplete "
                          f"(missing {', '.join(result.get('missing') or [])}). Run "
                          f"/capture-job jobs/{folder.name} to complete it.", "warn")
            except Exception as e:
                flash(f"Capture failed: {e}. Paste the description manually.", "warn")

        return redirect(url_for("view_job", slug=folder.name))

    @app.route("/jobs/<slug>")
    def view_job(slug):
        p = job_path(slug)
        job_yaml = read_text(p / "job.yaml")
        findings = _lint_findings(slug)
        st = derive_state(p)
        questions_doc = read_questions(p)
        return render_template(
            "job.html",
            slug=slug,
            job_yaml=job_yaml,
            job_yaml_parsed=yaml.safe_load(job_yaml) if job_yaml else {},
            description_md=read_text(p / "job-description.md"),
            description_html=md_to_html(read_text(p / "job-description.md")),
            analysis_md=read_text(p / "analysis.md"),
            analysis_html=md_to_html(read_text(p / "analysis.md")),
            resume_source=read_text(p / "resume-source.yaml"),
            custom_content=read_text(p / "custom-content.md"),
            has_resume=(p / "resume.docx").exists(),
            has_pdf=(p / "resume.pdf").exists(),
            has_html=(p / "resume.html").exists(),
            has_screenshot=(p / "job-screenshot.png").exists(),
            has_analysis=(p / "analysis.md").exists(),
            has_tailored=(p / "resume-source.yaml").exists(),
            has_custom=(p / "custom-content.md").exists()
                       and (p / "custom-content.md").stat().st_size > 0,
            state=st.state,
            state_explicit=st.is_explicit,
            next_step=st.next_step,
            capture_complete=st.capture_complete,
            capture_missing=list(st.capture_missing),
            progress=progress(p),
            applied=st.state in APPLIED_STATES,
            explicit_states=EXPLICIT_STATES,
            questions=questions_doc.get("questions") or [],
            has_questions=bool(questions_doc.get("questions")),
            lint_errors=[f for f in findings if f.severity == "error"],
            lint_warnings=[f for f in findings if f.severity == "warning"],
        )

    @app.route("/jobs/<slug>/state", methods=["POST"])
    def set_state(slug):
        p = job_path(slug)
        new_state = (request.form.get("state") or "").strip()
        if new_state == "auto":
            set_explicit_state(p, None)
            flash("Cleared explicit state — back to auto.", "info")
        elif new_state in EXPLICIT_STATES:
            set_explicit_state(p, new_state)
            flash(f"State → {new_state}.", "info")
        else:
            flash(f"Unknown state: {new_state}", "error")
        return redirect(url_for("view_job", slug=slug))

    @app.route("/jobs/<slug>/meta", methods=["POST"])
    def edit_meta(slug):
        """JSON {field, value} — inline-edit a job.yaml metadata field (company,
        role, etc.) from the Jobs table. Preserves the other fields."""
        from flask import jsonify
        p = job_path(slug) / "job.yaml"
        payload = request.get_json(silent=True) or {}
        field = (payload.get("field") or "").strip()
        value = payload.get("value", "")
        if field not in {"company", "role", "recruiter", "comp_range", "notes", "status"}:
            return jsonify({"error": f"field not editable: {field}"}), 400
        meta = {}
        if p.exists():
            try:
                meta = yaml.safe_load(p.read_text()) or {}
            except yaml.YAMLError as e:
                return jsonify({"error": f"job.yaml parse error: {e}"}), 400
        meta[field] = value
        p.write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
                     encoding="utf-8")
        return jsonify({"ok": True, "field": field, "value": value})

    @app.route("/jobs/<slug>/applied", methods=["POST"])
    def set_applied(slug):
        """Checkbox: mark the application submitted (→ Applied) or reopen."""
        p = job_path(slug)
        applied = request.form.get("applied") in ("on", "true", "1")
        set_explicit_state(p, "submitted" if applied else None)
        flash("Marked Application Submitted." if applied
              else "Reopened — no longer marked as applied.", "info")
        return redirect(url_for("view_job", slug=slug))

    @app.route("/jobs/<slug>/skip-questions", methods=["POST"])
    def skip_questions(slug):
        """Skip the background questions → advance to Ready to Apply."""
        jy = job_path(slug) / "job.yaml"
        meta = {}
        if jy.exists():
            try:
                meta = yaml.safe_load(jy.read_text()) or {}
            except yaml.YAMLError:
                meta = {}
        meta["questions_skipped"] = True
        jy.write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
                      encoding="utf-8")
        flash("Skipped background questions — moved to Ready to Apply.", "info")
        return redirect(url_for("view_job", slug=slug))

    @app.route("/jobs/<slug>/custom-content", methods=["POST"])
    def save_custom_content(slug):
        p = job_path(slug) / "custom-content.md"
        p.write_text(request.form.get("content", ""), encoding="utf-8")
        flash("Saved custom content. Re-run /tailor in Claude Code to pull it in.", "info")
        return redirect(url_for("view_job", slug=slug))

    @app.route("/jobs/<slug>/promote-custom", methods=["POST"])
    def promote_custom(slug):
        from datetime import date
        src = job_path(slug) / "custom-content.md"
        if not src.exists() or src.read_text().strip() == "":
            flash("Nothing to promote — custom-content.md is empty.", "warn")
            return redirect(url_for("view_job", slug=slug))
        narrative = root / "kitchen-sink" / "narrative.md"
        block = (
            f"\n\n---\n\n## Promoted from {slug} on {date.today().isoformat()}\n\n"
            + src.read_text(encoding="utf-8").strip() + "\n"
        )
        with narrative.open("a", encoding="utf-8") as f:
            f.write(block)
        flash("Appended to kitchen-sink/narrative.md with provenance.", "info")
        return redirect(url_for("view_job", slug=slug))

    @app.route("/jobs/<slug>/answers", methods=["POST"])
    def save_answers(slug):
        """Persist textarea answers back into background-questions.yaml."""
        p = job_path(slug)
        qf = p / "background-questions.yaml"
        if not qf.exists():
            flash("No background questions for this job yet — run /tailor.", "warn")
            return redirect(url_for("view_job", slug=slug))
        doc = yaml.safe_load(qf.read_text()) or {}
        changed = 0
        for q in doc.get("questions") or []:
            field = f"answer__{q.get('id')}"
            if field in request.form:
                new = request.form.get(field, "")
                if new != (q.get("answer") or ""):
                    q["answer"] = new
                    changed += 1
        qf.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                      encoding="utf-8")
        flash(f"Saved {changed} answer(s).", "info")
        return redirect(url_for("view_job", slug=slug))

    @app.route("/jobs/<slug>/promote-answers", methods=["POST"])
    def promote_answers(slug):
        """Append answered (and not-yet-promoted) questions to the dossier
        (kitchen-sink/narrative.md), with provenance, then mark them promoted
        so a second click can't duplicate them."""
        from datetime import date
        p = job_path(slug)
        qf = p / "background-questions.yaml"
        if not qf.exists():
            flash("No background questions to promote.", "warn")
            return redirect(url_for("view_job", slug=slug))
        doc = yaml.safe_load(qf.read_text()) or {}
        fresh = [q for q in (doc.get("questions") or [])
                 if (q.get("answer") or "").strip() and not q.get("promoted")]
        if not fresh:
            flash("Nothing new to promote — answer a question and Save first.", "warn")
            return redirect(url_for("view_job", slug=slug))
        today = date.today().isoformat()
        parts = [f"\n\n---\n\n## Background answers from {slug} on {today}\n"]
        for q in fresh:
            head = q.get("theme") or q.get("id")
            if q.get("attach_to"):
                head += f" — {q['attach_to']}"
            parts.append(f"\n### {head}\n")
            parts.append(f"\n_Q: {(q.get('prompt') or '').strip()}_\n")
            parts.append(f"\n{(q.get('answer') or '').strip()}\n")
        narrative = root / "kitchen-sink" / "narrative.md"
        with narrative.open("a", encoding="utf-8") as f:
            f.write("".join(parts))
        for q in fresh:
            q["promoted"] = today
        qf.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                      encoding="utf-8")
        flash(f"Appended {len(fresh)} answer(s) to kitchen-sink/narrative.md. "
              "Re-run /tailor to use them.", "info")
        return redirect(url_for("view_job", slug=slug))

    @app.route("/jobs/<slug>/answer", methods=["POST"])
    def save_answer(slug):
        """JSON {id, answer} — autosave a single background-question answer as the
        user moves between questions, so nothing is lost if the tab/server drops."""
        from flask import jsonify
        qf = job_path(slug) / "background-questions.yaml"
        payload = request.get_json(silent=True) or {}
        qid = (payload.get("id") or "").strip()
        if not qid:
            return jsonify({"error": "id required"}), 400
        if not qf.exists():
            return jsonify({"error": "no background-questions.yaml"}), 404
        try:
            doc = yaml.safe_load(qf.read_text()) or {}
        except yaml.YAMLError as e:
            return jsonify({"error": f"parse error: {e}"}), 400
        for q in doc.get("questions") or []:
            if q.get("id") == qid:
                q["answer"] = payload.get("answer", "")
                qf.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                              encoding="utf-8")
                return jsonify({"ok": True, "id": qid})
        return jsonify({"error": f"unknown question id: {qid}"}), 400

    @app.route("/jobs/<slug>/file/<fname>", methods=["POST"])
    def save_file(slug, fname):
        if fname not in {"job.yaml", "job-description.md", "resume-source.yaml",
                         "analysis.md", "custom-content.md"}:
            abort(400)
        p = job_path(slug) / fname
        content = request.form.get("content", "")
        p.write_text(content, encoding="utf-8")
        flash(f"Saved {fname}.", "info")
        return redirect(url_for("view_job", slug=slug))

    def _is_stale(artifact: Path, *sources: Path) -> bool:
        """An artifact is stale if any existing source is newer than it (or
        the artifact is missing)."""
        if not artifact.exists():
            return True
        a_mtime = artifact.stat().st_mtime
        for s in sources:
            if s.exists() and s.stat().st_mtime > a_mtime:
                return True
        return False

    def _ensure_fresh_job(slug: str, artifact: Path):
        """Rebuild all three job artifacts if any source is newer than this
        artifact. Cheap to call before serving a download."""
        folder = job_path(slug)
        sources = [
            folder / "resume-source.yaml",
            root / "kitchen-sink" / "profile.yaml",  # fallback when no tailored
        ]
        if _is_stale(artifact, *sources):
            try:
                build_job(folder, root=root)
            except (SystemExit, Exception):
                # If rebuild fails (e.g. lint error), serve whatever is on disk
                # so the user is never blocked from grabbing the previous file.
                pass

    def _ensure_fresh_general(artifact: Path):
        ks = root / "kitchen-sink" / "profile.yaml"
        if _is_stale(artifact, ks):
            try:
                build_general(root=root)
            except (SystemExit, Exception):
                pass

    @app.route("/jobs/<slug>/build", methods=["POST"])
    def build_job_route(slug):
        p = job_path(slug)
        try:
            out = build_job(p, root=root)
            msg = f"Built {out['docx'].name} + .html + .pdf."
            if out.get("warnings"):
                msg += f" {len(out['warnings'])} AI-tell warning(s) — review on the page."
            flash(msg, "info")
        except LintError as e:
            for f in e.findings[:8]:
                flash(f"Lint error [{f.code}] at {f.location}: {f.snippet}", "error")
            if len(e.findings) > 8:
                flash(f"…and {len(e.findings) - 8} more lint errors.", "error")
        except SystemExit as e:
            flash(f"Build failed: {e}", "error")
        return redirect(url_for("view_job", slug=slug))

    @app.route("/jobs/<slug>/resume.docx")
    def download_resume(slug):
        p = job_path(slug) / "resume.docx"
        _ensure_fresh_job(slug, p)
        if not p.exists():
            abort(404)
        return send_file(p, as_attachment=True, download_name=f"{slug}-resume.docx")

    @app.route("/jobs/<slug>/resume.pdf")
    def download_resume_pdf(slug):
        p = job_path(slug) / "resume.pdf"
        _ensure_fresh_job(slug, p)
        if not p.exists():
            abort(404)
        return send_file(p, as_attachment=True, download_name=f"{slug}-resume.pdf")

    @app.route("/jobs/<slug>/resume.html")
    def resume_html(slug):
        """Live read-only render from current resume-source.yaml (or kitchen
        sink fallback). Always reflects the latest saved edits — no rebuild
        needed."""
        from flask import Response
        profile = _profile_for(slug)
        if not profile:
            abort(404)
        return Response(render_html(profile), mimetype="text/html")

    @app.route("/jobs/<slug>/resume-edit.html")
    def resume_edit(slug):
        """Editable, contenteditable version. Not persisted to disk —
        regenerated from current resume-source.yaml (or kitchen-sink) on each
        request so it always reflects the latest saved state."""
        from flask import Response
        # If no resume-source.yaml yet, fall back to kitchen-sink so the user
        # can start editing immediately. First save will create the file.
        tailored = job_path(slug) / "resume-source.yaml"
        if tailored.exists():
            profile = yaml.safe_load(tailored.read_text()) or {}
        else:
            ks = root / "kitchen-sink" / "profile.yaml"
            profile = yaml.safe_load(ks.read_text()) if ks.exists() else {}
        html = render_html(
            profile,
            editable=True,
            save_url=url_for("edit_field", slug=slug),
            delete_url=url_for("delete_field", slug=slug),
        )
        return Response(html, mimetype="text/html")

    def _load_or_seed_tailored(slug: str) -> tuple[Path, dict]:
        """Return (path, profile) — loading resume-source.yaml or seeding it
        from the kitchen sink for first-edit on a fresh job."""
        tailored = job_path(slug) / "resume-source.yaml"
        if tailored.exists():
            return tailored, (yaml.safe_load(tailored.read_text()) or {})
        ks = root / "kitchen-sink" / "profile.yaml"
        if not ks.exists():
            return tailored, {}
        return tailored, (yaml.safe_load(ks.read_text()) or {})

    @app.route("/jobs/<slug>/edit-field", methods=["POST"])
    def edit_field(slug):
        """JSON POST {path, text}. Updates resume-source.yaml at the given
        dotted path. Auto-creates resume-source.yaml from kitchen-sink the
        first time."""
        from flask import jsonify
        payload = request.get_json(silent=True) or {}
        path = (payload.get("path") or "").strip()
        text = payload.get("text", "")
        if not path:
            return jsonify({"error": "path required"}), 400

        tailored, profile = _load_or_seed_tailored(slug)
        if not profile:
            return jsonify({"error": "no kitchen-sink to base edits on"}), 400

        try:
            # Items: special-case the comma-joined skills list back into a list.
            if path.endswith(".items"):
                items = [s.strip() for s in str(text).split(",") if s.strip()]
                set_by_path(profile, path, items)
            else:
                set_by_path(profile, path, text)
        except (KeyError, IndexError, TypeError, ValueError) as e:
            return jsonify({"error": f"{type(e).__name__}: {e}"}), 400

        tailored.write_text(yaml.safe_dump(profile, sort_keys=False),
                            encoding="utf-8")
        return jsonify({"ok": True, "path": path})

    @app.route("/jobs/<slug>/delete-field", methods=["POST"])
    def delete_field(slug):
        """JSON POST {path}. Removes the addressed item:
          - list element at experience.N or experience.N.bullets.M  → pop
          - entire section list (experience, skills, certifications, …)  → []
          - leaf string (summary)  → ''
        Refuses unknown paths to avoid silent damage."""
        from flask import jsonify
        from yaml_path import _split, _step  # internal helpers
        payload = request.get_json(silent=True) or {}
        path = (payload.get("path") or "").strip()
        if not path:
            return jsonify({"error": "path required"}), 400

        tailored, profile = _load_or_seed_tailored(slug)
        if not profile:
            return jsonify({"error": "no kitchen-sink to base edits on"}), 400

        try:
            parts = _split(path)
            parent = profile
            for p in parts[:-1]:
                parent = _step(parent, p)
            last = parts[-1]
            if isinstance(parent, list):
                idx = int(last)
                if not (0 <= idx < len(parent)):
                    raise IndexError(idx)
                parent.pop(idx)
            elif isinstance(parent, dict):
                if last not in parent:
                    raise KeyError(last)
                cur = parent[last]
                if isinstance(cur, list):
                    parent[last] = []
                elif isinstance(cur, str):
                    parent[last] = ""
                else:
                    # remove the leaf entirely for scalar non-strings (rare)
                    del parent[last]
            else:
                raise TypeError(f"cannot delete from {type(parent).__name__}")
        except (KeyError, IndexError, TypeError, ValueError) as e:
            return jsonify({"error": f"{type(e).__name__}: {e}"}), 400

        tailored.write_text(yaml.safe_dump(profile, sort_keys=False),
                            encoding="utf-8")
        return jsonify({"ok": True, "path": path})

    @app.route("/jobs/<slug>/screenshot.png")
    def screenshot(slug):
        p = job_path(slug) / "job-screenshot.png"
        if not p.exists():
            abort(404)
        return send_file(p)

    @app.route("/general")
    def general():
        gp = root / "general-resume" / "general-resume.docx"
        gh = root / "general-resume" / "general-resume.html"
        gpdf = root / "general-resume" / "general-resume.pdf"
        ks = root / "kitchen-sink" / "profile.yaml"
        findings = _lint_findings(None)
        return render_template(
            "general.html",
            built=gp.exists(),
            mtime=gp.stat().st_mtime if gp.exists() else None,
            has_html=gh.exists(),
            has_pdf=gpdf.exists(),
            kitchen_sink_yaml=read_text(ks),
            lint_errors=[f for f in findings if f.severity == "error"],
            lint_warnings=[f for f in findings if f.severity == "warning"],
        )

    @app.route("/general/build", methods=["POST"])
    def build_general_route():
        try:
            out = build_general(root=root)
            msg = f"Built {out['docx'].name} + .html + .pdf."
            if out.get("warnings"):
                msg += f" {len(out['warnings'])} AI-tell warning(s)."
            flash(msg, "info")
        except LintError as e:
            for f in e.findings[:8]:
                flash(f"Lint error [{f.code}] at {f.location}: {f.snippet}", "error")
            if len(e.findings) > 8:
                flash(f"…and {len(e.findings) - 8} more lint errors.", "error")
        except SystemExit as e:
            flash(f"Build failed: {e}", "error")
        return redirect(url_for("general"))

    @app.route("/general/resume.docx")
    def download_general():
        p = root / "general-resume" / "general-resume.docx"
        _ensure_fresh_general(p)
        if not p.exists():
            abort(404)
        return send_file(p, as_attachment=True, download_name="resume.docx")

    @app.route("/general/resume.pdf")
    def download_general_pdf():
        p = root / "general-resume" / "general-resume.pdf"
        _ensure_fresh_general(p)
        if not p.exists():
            abort(404)
        return send_file(p, as_attachment=True, download_name="resume.pdf")

    @app.route("/general/resume.html")
    def general_html():
        """Live read-only render from current kitchen-sink/profile.yaml."""
        from flask import Response
        profile = _profile_for(None)
        if not profile:
            abort(404)
        return Response(render_html(profile), mimetype="text/html")

    @app.route("/general/kitchen-sink", methods=["POST"])
    def save_kitchen_sink():
        p = root / "kitchen-sink" / "profile.yaml"
        p.write_text(request.form.get("content", ""), encoding="utf-8")
        flash("Saved kitchen sink.", "info")
        return redirect(url_for("general"))

    @app.route("/favicon.ico")
    def favicon():
        return send_file(_HERE / "static" / "favicon.svg",
                         mimetype="image/svg+xml")

    @app.route("/install")
    def install_page():
        """Serve the standalone, beginner-friendly install/share page."""
        p = _DEFAULT_ROOT / "docs" / "install.html"
        if not p.exists():
            abort(404)
        return send_file(p)

    @app.route("/img/<path:fname>")
    def docs_img(fname):
        """Serve images referenced by the install page (docs/img/)."""
        p = (_DEFAULT_ROOT / "docs" / "img" / fname).resolve()
        if (_DEFAULT_ROOT / "docs" / "img").resolve() not in p.parents or not p.exists():
            abort(404)
        return send_file(p)

    # ---- Build-your-dossier page ----

    def _sources_dir() -> Path:
        d = root / "kitchen-sink" / "sources"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _dossier_ready() -> dict:
        """Is profile.yaml filled in enough to build a standard resume?"""
        p = root / "kitchen-sink" / "profile.yaml"
        if not p.exists():
            return {"ready": False, "missing": ["your profile (run setup first)"]}
        try:
            prof = yaml.safe_load(p.read_text()) or {}
        except yaml.YAMLError:
            return {"ready": False, "missing": ["a valid profile.yaml (it has a syntax error)"]}
        name = ((prof.get("identity") or {}).get("name") or "").strip()
        summary = (prof.get("summary") or "").strip()
        has_exp = any("TODO" not in ((e.get("company") or "") + (e.get("title") or ""))
                      for e in (prof.get("experience") or []))
        missing = []
        if not name or "TODO" in name:
            missing.append("your name")
        if not summary or summary.startswith("TODO"):
            missing.append("a professional summary")
        if not has_exp:
            missing.append("at least one real work experience")
        return {"ready": not missing, "missing": missing}

    @app.route("/dossier")
    def dossier_page():
        ks = root / "kitchen-sink"
        srcs = _sources_dir()
        return render_template(
            "dossier.html",
            ready=_dossier_ready(),
            sources=sorted(p.name for p in srcs.iterdir() if p.is_file()),
            linkedin_files=sorted(p.name for p in (ks / "linkedin").glob("*") if p.is_file())
                            if (ks / "linkedin").exists() else [],
        )

    @app.route("/dossier/upload", methods=["POST"])
    def dossier_upload():
        saved = []
        for f in request.files.getlist("files"):
            if not f or not f.filename:
                continue
            name = secure_filename(f.filename)
            dest = (root / "kitchen-sink" / "linkedin") if name.lower().endswith(".zip") else _sources_dir()
            dest.mkdir(parents=True, exist_ok=True)
            f.save(str(dest / name))
            saved.append(name)
        flash(f"Saved {len(saved)} file(s) into your dossier: {', '.join(saved)}"
              if saved else "No files were selected.", "info" if saved else "warn")
        return redirect(url_for("dossier_page"))

    @app.route("/dossier/paste-text", methods=["POST"])
    def dossier_paste_text():
        from datetime import date
        text = (request.form.get("text") or "").strip()
        label = (request.form.get("label") or "").strip() or "Pasted note"
        if not text:
            flash("Nothing to add.", "warn")
            return redirect(url_for("dossier_page"))
        nar = root / "kitchen-sink" / "narrative.md"
        nar.parent.mkdir(parents=True, exist_ok=True)
        with nar.open("a", encoding="utf-8") as fh:
            fh.write(f"\n\n---\n\n## {label} (added {date.today().isoformat()})\n\n{text}\n")
        flash("Added to your dossier (narrative.md).", "info")
        return redirect(url_for("dossier_page"))

    @app.route("/dossier/paste-image", methods=["POST"])
    def dossier_paste_image():
        from flask import jsonify
        from datetime import datetime
        import base64
        import re as _re
        m = _re.match(r"data:image/(png|jpe?g|webp);base64,(.+)$",
                      (request.get_json(silent=True) or {}).get("image_data_url", ""), _re.S)
        if not m:
            return jsonify({"error": "no image data found"}), 400
        ext = "jpg" if m.group(1).startswith("jp") else m.group(1)
        name = f"pasted-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{ext}"
        try:
            (_sources_dir() / name).write_bytes(base64.b64decode(m.group(2)))
        except Exception as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "name": name})

    return app


def main():
    app = create_app()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5050")), debug=True)


if __name__ == "__main__":
    main()
