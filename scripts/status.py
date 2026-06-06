"""Workflow state for a job folder.

Auto-derived states (from file presence) drive the "what's next" prompt.
Explicit states (set by user button) override the derived value once the
human takes ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from job_validation import validate_job_file


# Explicit states the user can set via buttons.
EXPLICIT_STATES = ("ready", "submitted", "interviewing", "closed")

# All possible states (derived + explicit).
ALL_STATES = (
    "needs-description",
    "needs-tailoring",
    "needs-build",
    "needs-review",
    *EXPLICIT_STATES,
)

# CTAs shown on the job page for each derived (auto) state.
NEXT_STEP = {
    "needs-description": "Paste or capture the job posting into job-description.md.",
    "needs-tailoring":   "In Claude Code, run /tailor jobs/<this folder>.",
    "needs-build":       "Click Build resume to render the docx / pdf / html.",
    "needs-review":      "Review the preview, fix any lint warnings, then Mark as approved.",
    "ready":             "Submit the application, then Mark as submitted.",
    "submitted":         "Waiting on a response. Mark as interviewing if you hear back.",
    "interviewing":      "Track interview rounds in the Notes field of job.yaml.",
    "closed":            "Application closed.",
}


@dataclass(frozen=True)
class JobState:
    state: str           # one of ALL_STATES
    is_explicit: bool    # True if set by user, False if auto-derived
    next_step: str
    capture_complete: bool = True   # False if the captured posting is incomplete
    capture_missing: tuple = ()     # which sections are missing, if any


def _read_yaml(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError:
        return {}


_PASTE_STUB_MARKER = "paste the job description here"


def _description_looks_real(p: Path) -> bool:
    if not p.exists():
        return False
    text = p.read_text(encoding="utf-8")
    if _PASTE_STUB_MARKER in text.lower():
        return False
    # crude: count words outside HTML comments and headers
    body_words = [w for w in text.split() if not w.startswith(("#", "<!--", "-->", "<", "_"))]
    return len(body_words) > 80


def derive_state(folder: Path) -> JobState:
    job = _read_yaml(folder / "job.yaml")
    desc = validate_job_file(folder / "job-description.md")
    complete = bool(desc.get("complete"))
    missing = tuple(desc.get("missing") or ())

    explicit = (job.get("state") or "").strip()
    if explicit in EXPLICIT_STATES:
        return JobState(explicit, True, NEXT_STEP.get(explicit, ""),
                        complete, missing)

    if not desc.get("present"):
        return JobState("needs-description", False,
                        NEXT_STEP["needs-description"], complete, missing)

    # A present-but-incomplete capture still advances through the workflow, but
    # carries capture_complete=False so the UI flags it loudly (chip + banner)
    # and /capture-job / /tailor can prompt to finish it. We don't hard-block on
    # the heuristic — it can misjudge an unusual but valid posting; the firm
    # "don't tailor a partial posting" gate lives in the /tailor skill instead.
    if not (folder / "resume-source.yaml").exists():
        return JobState("needs-tailoring", False, NEXT_STEP["needs-tailoring"],
                        complete, missing)

    docx = folder / "resume.docx"
    src = folder / "resume-source.yaml"
    if not docx.exists() or docx.stat().st_mtime < src.stat().st_mtime:
        return JobState("needs-build", False, NEXT_STEP["needs-build"], complete, missing)

    return JobState("needs-review", False, NEXT_STEP["needs-review"], complete, missing)


def set_explicit_state(folder: Path, state: str | None) -> JobState:
    """Persist an explicit state into job.yaml. Pass None to clear it."""
    if state is not None and state not in EXPLICIT_STATES:
        raise ValueError(f"Not an explicit state: {state}")
    job = _read_yaml(folder / "job.yaml")
    if state is None:
        job.pop("state", None)
    else:
        job["state"] = state
    (folder / "job.yaml").write_text(yaml.safe_dump(job, sort_keys=False),
                                     encoding="utf-8")
    return derive_state(folder)


# --- application progress (7-stage lifecycle for the job page) ------------

# Explicit states that count as "applied" — excluded from bulk /tailor ops.
APPLIED_STATES = ("submitted", "interviewing", "closed")

# (label, job-page anchor) in lifecycle order.
PROGRESS_STAGES = (
    ("New", "#capture"),
    ("Extracting", "#capture"),
    ("File Created", "#tailoring"),
    ("Tailoring", "#tailoring"),
    ("Follow Up Questions", "#followup"),
    ("Ready to Apply", "#apply"),
    ("Application Submitted", "#apply"),
)


@dataclass(frozen=True)
class Progress:
    current: int
    current_label: str
    stages: tuple   # tuple of {label, anchor, status: done|current|todo}


def _unanswered_questions(folder: Path) -> int:
    qf = folder / "background-questions.yaml"
    if not qf.exists():
        return 0
    try:
        doc = yaml.safe_load(qf.read_text()) or {}
    except yaml.YAMLError:
        return 0
    return sum(
        1 for q in (doc.get("questions") or [])
        if not (q.get("answer") or "").strip() and not q.get("promoted")
    )


def is_applied(folder: Path) -> bool:
    job = _read_yaml(folder / "job.yaml")
    return (job.get("state") or "") in APPLIED_STATES or bool(job.get("applied"))


def progress(folder: Path) -> Progress:
    """Where the application sits in the 7-stage lifecycle, for the progress bar."""
    job = _read_yaml(folder / "job.yaml")
    applied = (job.get("state") or "") in APPLIED_STATES or bool(job.get("applied"))
    desc = validate_job_file(folder / "job-description.md")
    has_tailored = (folder / "resume-source.yaml").exists()
    skipped = bool(job.get("questions_skipped"))

    if applied:
        cur = 6
    elif not desc.get("present"):
        cur = 1 if (folder / "job-description.md").exists() else 0
    elif not desc.get("complete"):
        cur = 1
    elif not has_tailored:
        cur = 2
    elif _unanswered_questions(folder) > 0 and not skipped:
        cur = 4
    else:
        cur = 5

    stages = tuple(
        {"label": label, "anchor": anchor,
         "status": "done" if i < cur else ("current" if i == cur else "todo")}
        for i, (label, anchor) in enumerate(PROGRESS_STAGES)
    )
    return Progress(cur, PROGRESS_STAGES[cur][0], stages)
