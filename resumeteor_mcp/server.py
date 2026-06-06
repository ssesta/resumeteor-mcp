"""Resumeteor MCP server.

Drive your local resume dossier from any MCP client (Claude Desktop, Claude
Code, Cursor, VS Code…). The chat client does the *reasoning* — tailoring,
critique — on the user's own subscription; this server does the deterministic
work: file I/O over the dossier, job capture, completeness validation, and the
document build. It reuses the project's existing scripts, so there's one source
of truth for the logic.

Run:  resumeteor-mcp           (stdio transport — what MCP clients launch)
Data: ~/Resumeteor by default  (override with RESUMETEOR_HOME)
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# --- locate the bundled project + the user's dossier ---------------------

_PKG = Path(__file__).resolve().parent
# Installed wheels bundle the project under _bundled/; in the source repo it's
# the package's parent directory.
_BUNDLED = _PKG / "_bundled"
_REPO = _BUNDLED if _BUNDLED.exists() else _PKG.parent
sys.path.insert(0, str(_REPO / "scripts"))

HOME = Path(os.environ.get("RESUMETEOR_HOME", Path.home() / "Resumeteor")).expanduser()
os.environ["JOBSEARCH_ROOT"] = str(HOME)   # the scripts read this to find the dossier

import yaml  # noqa: E402

mcp = FastMCP("resumeteor")


# --- helpers -------------------------------------------------------------

def _jobs_dir() -> Path:
    return HOME / "jobs"


def _job_path(slug: str) -> Path:
    p = (_jobs_dir() / slug).resolve()
    if _jobs_dir().resolve() not in p.parents or not p.is_dir():
        raise ValueError(f"Unknown job folder: {slug}")
    return p


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _command_prompt(name: str, arguments: str = "") -> str:
    """Return a bundled .claude/commands/<name>.md as an MCP prompt, with
    $ARGUMENTS filled and a note to use this server's tools for file I/O."""
    md = _read(_REPO / ".claude" / "commands" / f"{name}.md")
    md = md.replace("$ARGUMENTS", arguments)
    note = (
        "You are running inside an MCP client with the **resumeteor** server. "
        "Use its tools for all file access — `get_dossier`, `get_job`, "
        "`save_resume_source`, `save_analysis`, `save_background_questions`, "
        "`build_resume` — instead of shell or local paths. Do the reasoning "
        "yourself (you are the subscription-billed model). Then follow:\n\n"
    )
    return note + md


# --- tools: setup & dossier ----------------------------------------------

@mcp.tool()
def setup_dossier() -> str:
    """Create the local dossier (kitchen-sink profile + narrative, and the jobs/
    and general-resume/ folders) under RESUMETEOR_HOME if it doesn't exist yet.
    Safe to run repeatedly; never overwrites your data. Run this once first."""
    actions = []
    for rel in ("kitchen-sink", "jobs", "general-resume"):
        d = HOME / rel
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            actions.append(f"created {rel}/")
    tpl = _REPO / "templates" / "kitchen-sink"
    for name in ("profile.yaml", "narrative.md"):
        dest = HOME / "kitchen-sink" / name
        if dest.exists():
            actions.append(f"kept existing kitchen-sink/{name}")
        elif (tpl / name).exists():
            shutil.copyfile(tpl / name, dest)
            actions.append(f"seeded kitchen-sink/{name} from template")
    return (f"Dossier at {HOME}\n  - " + "\n  - ".join(actions) +
            "\n\nNext: fill in kitchen-sink/profile.yaml and narrative.md "
            "(paste from your résumé / LinkedIn export), then add a job with add_job(url).")


@mcp.tool()
def get_dossier() -> dict:
    """Return your canonical dossier: profile.yaml and narrative.md (the source
    of truth the tailoring reads from)."""
    ks = HOME / "kitchen-sink"
    return {"profile_yaml": _read(ks / "profile.yaml"),
            "narrative_md": _read(ks / "narrative.md")}


@mcp.tool()
def update_profile(profile_yaml: str) -> str:
    """Overwrite kitchen-sink/profile.yaml with new YAML content."""
    yaml.safe_load(profile_yaml)  # validate it parses
    (HOME / "kitchen-sink" / "profile.yaml").write_text(profile_yaml, encoding="utf-8")
    return "Saved kitchen-sink/profile.yaml."


@mcp.tool()
def append_to_dossier(markdown: str) -> str:
    """Append long-form material (a STAR story, answers to background questions,
    extra context) to kitchen-sink/narrative.md so future tailoring is stronger."""
    nar = HOME / "kitchen-sink" / "narrative.md"
    with nar.open("a", encoding="utf-8") as f:
        f.write("\n\n" + markdown.strip() + "\n")
    return "Appended to kitchen-sink/narrative.md."


# --- tools: jobs ---------------------------------------------------------

@mcp.tool()
def list_jobs() -> list[dict]:
    """List all job applications with company, role, capture completeness, and
    progress stage."""
    import status as _status
    from job_validation import validate_job_file
    out = []
    if not _jobs_dir().exists():
        return out
    for d in sorted(_jobs_dir().iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta = {}
        jy = d / "job.yaml"
        if jy.exists():
            try:
                meta = yaml.safe_load(jy.read_text()) or {}
            except yaml.YAMLError:
                meta = {}
        out.append({
            "slug": d.name,
            "company": meta.get("company", ""),
            "role": meta.get("role", ""),
            "stage": _status.progress(d).current_label,
            "capture_complete": validate_job_file(d / "job-description.md")["complete"],
            "tailored": (d / "resume-source.yaml").exists(),
        })
    return out


@mcp.tool()
def add_job(url: str, company: str = "", role: str = "") -> dict:
    """Scaffold a new job folder from a posting URL and capture the description
    (structured ATS APIs → requests → headless browser, validated for
    completeness). Returns the slug and capture status."""
    import new_job as _newjob
    from capture_job import capture
    folder = _newjob.make_job_folder(url, company or None, role or None, root=HOME)
    _newjob.write_job_yaml(folder, url, company or None, role or None)
    result = capture(url, folder)
    return {"slug": folder.name, **result,
            "note": ("Capture incomplete — open the screenshot and extract the posting, "
                     "or paste it into the job's description." if not result.get("complete")
                     else "Captured complete.")}


@mcp.tool()
def get_job(slug: str) -> dict:
    """Return everything about one job: the posting, Claude's analysis, the
    tailored resume source, background questions, capture completeness, and stage."""
    import status as _status
    from job_validation import validate_job_file
    p = _job_path(slug)
    v = validate_job_file(p / "job-description.md")
    return {
        "slug": slug,
        "job_yaml": _read(p / "job.yaml"),
        "job_description_md": _read(p / "job-description.md"),
        "analysis_md": _read(p / "analysis.md"),
        "resume_source_yaml": _read(p / "resume-source.yaml"),
        "background_questions_yaml": _read(p / "background-questions.yaml"),
        "custom_content_md": _read(p / "custom-content.md"),
        "capture_complete": v["complete"],
        "capture_missing": v["missing"],
        "stage": _status.progress(p).current_label,
    }


@mcp.tool()
def save_analysis(slug: str, analysis_md: str) -> str:
    """Write the job fit analysis (analysis.md) produced during tailoring."""
    _job_path(slug).joinpath("analysis.md").write_text(analysis_md, encoding="utf-8")
    return f"Saved analysis.md for {slug}."


@mcp.tool()
def save_resume_source(slug: str, resume_source_yaml: str) -> str:
    """Write the tailored resume source (resume-source.yaml, same schema as
    profile.yaml). Validated as YAML before saving."""
    yaml.safe_load(resume_source_yaml)
    _job_path(slug).joinpath("resume-source.yaml").write_text(resume_source_yaml, encoding="utf-8")
    return f"Saved resume-source.yaml for {slug}. Call build_resume('{slug}') to render."


@mcp.tool()
def save_background_questions(slug: str, background_questions_yaml: str) -> str:
    """Write background-questions.yaml — the gaps/clarifications to ask the user,
    which they answer to enrich the dossier for future tailoring."""
    yaml.safe_load(background_questions_yaml)
    _job_path(slug).joinpath("background-questions.yaml").write_text(
        background_questions_yaml, encoding="utf-8")
    return f"Saved background-questions.yaml for {slug}."


@mcp.tool()
def build_resume(slug: str) -> dict:
    """Render the tailored resume to .docx, .pdf, and .html from resume-source.yaml.
    (.pdf needs a one-time `playwright install chromium`.)"""
    import build_resume as _build
    p = _job_path(slug)
    try:
        paths = _build.build_job(p, root=HOME)
        return {ext: str(v) for ext, v in paths.items() if ext in ("docx", "pdf", "html")}
    except Exception as e:
        # docx/html are written before the pdf step, so return whatever exists.
        out = {ext: str(p / f"resume.{ext}") for ext in ("docx", "html")
               if (p / f"resume.{ext}").exists()}
        if not out:
            raise
        out["note"] = (f"Built docx/html; PDF step failed ({type(e).__name__}). "
                       "Run `playwright install chromium` to enable PDF.")
        return out


# --- prompts: the reasoning procedures (run by the client's model) --------

@mcp.prompt()
def tailor(slug: str) -> str:
    """Tailor a resume for a job folder — the full honest tailoring procedure."""
    return _command_prompt("tailor", f"jobs/{slug}")


@mcp.prompt()
def critique(slug: str) -> str:
    """Critique a tailored resume against the job description."""
    return _command_prompt("critique", f"jobs/{slug}")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
