"""Heuristic completeness validation for a captured job posting.

Kept dependency-free (no requests / bs4 / LLM) so it can be imported anywhere —
capture_job.py, status.py, and the Flask UI all share ONE definition of "is this
job file complete enough to tailor against?"

A usable posting must have, at minimum:
  - a substantive description (enough prose),
  - duties / responsibilities,
  - requirements / qualifications (skills & experience).

This is a cheap first-pass gate. The /capture-job skill does a richer semantic
check and the universal screenshot→LLM extraction when this flags a gap.
"""

from __future__ import annotations

import re
from pathlib import Path

MIN_DESCRIPTION_WORDS = 150

_DUTIES_RE = re.compile(
    r"responsib|what you(?:'|’)?ll do|what you will do|what you(?:'|’)?ll be doing|"
    r"in this role|your role|day[- ]to[- ]day|\bduties\b|the role|key accountab|"
    r"what you(?:'|’)?ll own|you will\b", re.I)

_REQUIREMENTS_RE = re.compile(
    r"requirement|qualif|what you(?:'|’)?ll need|what you need|you have\b|"
    r"years.{0,4}experience|experience (?:in|with|leading|building)|\bskills\b|"
    r"must[- ]have|we(?:'|’)?re looking for|about you|minimum|preferred|"
    r"you bring|background in", re.I)

_PASTE_STUB_MARKER = "paste the job description here"


def _word_count(text: str) -> int:
    return len((text or "").split())


def description_body(md: str) -> str:
    """Strip capture scaffolding (HTML comments, the incomplete-capture banner
    blockquote, and italic boilerplate) so validation sees only the posting —
    not the banner, which itself names 'duties'/'requirements'."""
    md = re.sub(r"<!--.*?-->", " ", md or "", flags=re.S)
    out = []
    for line in md.splitlines():
        s = line.lstrip()
        if s.startswith(">"):                      # banner blockquote
            continue
        if s.startswith("_") and s.rstrip().endswith("_"):   # "_Verify…_" boilerplate
            continue
        out.append(line)
    return "\n".join(out)


def validate_job_text(text: str) -> dict:
    """Return {complete, missing, words} for already-extracted posting text."""
    words = _word_count(text)
    missing = []
    if words < MIN_DESCRIPTION_WORDS:
        missing.append("description")
    if not _DUTIES_RE.search(text or ""):
        missing.append("duties")
    if not _REQUIREMENTS_RE.search(text or ""):
        missing.append("requirements")
    return {"complete": not missing, "missing": missing, "words": words}


def validate_job_file(path) -> dict:
    """Validate a job-description.md on disk. Returns {present, complete, missing,
    words}. `present` is False for a missing file or the paste stub."""
    p = Path(path)
    if not p.exists():
        return {"present": False, "complete": False, "words": 0,
                "missing": ["description", "duties", "requirements"]}
    md = p.read_text(encoding="utf-8")
    if _PASTE_STUB_MARKER in md.lower():
        return {"present": False, "complete": False, "words": 0,
                "missing": ["description", "duties", "requirements"]}
    v = validate_job_text(description_body(md))
    v["present"] = v["words"] >= 80
    return v
