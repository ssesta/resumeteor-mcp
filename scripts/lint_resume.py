"""Quality lint for rendered resume content.

Two tiers:
  - ERRORS — encoding/template artifacts that should never ship. Build fails.
  - WARNINGS — phrases commonly overused by LLMs ("AI-tells"). Build succeeds
    but the UX shows them prominently so a human can decide.

Run on the same profile dict that the renderers consume, so issues are caught
before any .docx / .html / .pdf is written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


# ----- ERROR patterns (hard fail) -----------------------------------------

# HTML / XML entity that leaked into a text field. We intentionally allow ·,
# em-dash, smart quotes — those are real Unicode and fine in the final doc.
_ENTITY = re.compile(r"&(?:[a-zA-Z]{2,12}|#\d{2,5}|#x[0-9a-fA-F]{2,5});")

# Common mojibake — UTF-8 read as Latin-1 then re-encoded.
_MOJIBAKE = re.compile(r"Ã©|Ã¨|Ã¢|â€™|â€œ|â€|â€“|â€”|Â·|Â ")

# Raw template syntax that should have been expanded.
_TEMPLATE = re.compile(r"\{\{[^}]+\}\}|\{%[^%]+%\}")

# Backslash-u literals that didn't get decoded.
_RAW_UNICODE_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}|\\x[0-9a-fA-F]{2}")

# TODO / FIXME markers — these should be resolved before a resume goes out.
_TODO_MARKER = re.compile(r"\b(TODO|FIXME|XXX|TBD|TK)\b")

# Placeholder text that suggests the field was never filled.
_LOREM = re.compile(r"\blorem ipsum\b", re.I)


ERROR_CHECKS = [
    ("html_entity_leak",
     "HTML/XML entity in rendered text — likely a double-escape bug.",
     _ENTITY),
    ("mojibake",
     "Mojibake (mis-decoded Unicode) detected.",
     _MOJIBAKE),
    ("raw_template_syntax",
     "Unexpanded template syntax in rendered text.",
     _TEMPLATE),
    ("raw_unicode_escape",
     r"Raw \uXXXX or \xNN escape in rendered text.",
     _RAW_UNICODE_ESCAPE),
    ("todo_marker",
     "TODO/FIXME/TBD/TK marker — resolve before sending.",
     _TODO_MARKER),
    ("lorem_ipsum",
     "Placeholder text 'lorem ipsum' detected.",
     _LOREM),
]


# ----- WARNING patterns (AI-tells) ----------------------------------------

# Words/phrases LLMs over-produce. Many can be legitimately used by a human,
# so we flag for review rather than block. Keep this list tight — false
# positives quickly become noise that gets ignored.
AI_TELLS = [
    # Verbs LLMs reach for
    "leverage", "leveraged", "leveraging",
    "spearhead", "spearheaded", "spearheading",
    "orchestrate", "orchestrated", "orchestrating",
    "elevate", "elevated", "elevating",
    "delve", "delved", "delving",
    "embark", "embarked",
    "navigate", "navigating",          # often paired with "complexities"
    "unleash", "unleashed",
    "harness", "harnessed",
    "showcase", "showcased",
    "tapestry", "tapestries",
    "underscores", "underscoring",
    "pivotal",
    "seamless", "seamlessly",
    "robust",                          # warn — not auto-bad, but overused
    # Adjective inflation
    "cutting-edge", "best-in-class", "world-class",
    "transformative", "transformational",
    "game-changing", "game-changer",
    "innovative", "innovate",
    "synergy", "synergies", "synergistic",
    "holistic", "holistically",
    "paradigm",
    # Phrases
    "in today's fast-paced",
    "navigate the complexities",
    "deep dive", "deep-dive",
    "thought leader", "thought leadership",
    "passionate about",
    "results-driven", "results-oriented",
    "wide range of",
    "diverse range of",
    "ever-evolving",
    "rapidly evolving",
]

# Lower-case for matching; use word-boundary so "synergy" doesn't match "synergyless"
_AI_TELL_PATTERNS = [
    (phrase, re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE))
    for phrase in AI_TELLS
]


# ----- Walker -------------------------------------------------------------

@dataclass
class Finding:
    severity: str       # "error" | "warning"
    code: str           # e.g. "html_entity_leak", "ai_tell"
    message: str
    location: str       # dotted path: "experience[0].bullets[2].text"
    snippet: str        # the matched text in context (~50 chars)


def _iter_text_fields(profile: dict) -> Iterable[tuple[str, str]]:
    """Yield (dotted-location, text) for every textual field the renderers
    will output. Mirrors what the renderers actually emit."""
    identity = profile.get("identity") or {}
    for k in ("name", "headline", "location", "email", "phone", "website",
              "linkedin", "github"):
        if v := identity.get(k):
            yield f"identity.{k}", str(v)

    if v := profile.get("summary"):
        yield "summary", str(v)

    for i, role in enumerate(profile.get("experience") or []):
        prefix = f"experience[{i}]"
        for k in ("company", "location", "title", "blurb"):
            if v := role.get(k):
                yield f"{prefix}.{k}", str(v)
        for j, b in enumerate(role.get("bullets") or []):
            if isinstance(b, str):
                yield f"{prefix}.bullets[{j}]", b
            elif isinstance(b, dict) and (t := b.get("text")):
                yield f"{prefix}.bullets[{j}].text", str(t)

    for i, edu in enumerate(profile.get("education") or []):
        prefix = f"education[{i}]"
        for k in ("institution", "location", "degree", "field"):
            if v := edu.get(k):
                yield f"{prefix}.{k}", str(v)

    for i, g in enumerate(profile.get("skills") or []):
        prefix = f"skills[{i}]"
        if v := g.get("group"):
            yield f"{prefix}.group", str(v)
        for j, item in enumerate(g.get("items") or []):
            yield f"{prefix}.items[{j}]", str(item)

    for i, c in enumerate(profile.get("certifications") or []):
        prefix = f"certifications[{i}]"
        for k in ("name", "issuer"):
            if v := c.get(k):
                yield f"{prefix}.{k}", str(v)


def _snippet(text: str, m: re.Match, context: int = 30) -> str:
    start = max(0, m.start() - context)
    end = min(len(text), m.end() + context)
    s = text[start:end].replace("\n", " ")
    if start > 0:
        s = "…" + s
    if end < len(text):
        s = s + "…"
    return s


def lint(profile: dict) -> list[Finding]:
    findings: list[Finding] = []

    for loc, text in _iter_text_fields(profile):
        # Errors
        for code, message, pat in ERROR_CHECKS:
            for m in pat.finditer(text):
                findings.append(Finding(
                    severity="error", code=code, message=message,
                    location=loc, snippet=_snippet(text, m),
                ))
        # Warnings (AI tells) — only on long-form fields, not single words
        # like institution name.
        if loc.endswith(".text") or loc.endswith(".blurb") or loc == "summary" \
                or loc == "identity.headline":
            for phrase, pat in _AI_TELL_PATTERNS:
                for m in pat.finditer(text):
                    findings.append(Finding(
                        severity="warning", code="ai_tell",
                        message=f"AI-tell phrase: '{phrase}'.",
                        location=loc, snippet=_snippet(text, m),
                    ))
    return findings


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == "error"]


def warnings(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == "warning"]


class LintError(SystemExit):
    """Raised when a build is blocked by lint errors."""
    def __init__(self, findings: list[Finding]):
        self.findings = findings
        msg = "Resume lint blocked the build:\n" + "\n".join(
            f"  [{f.code}] {f.location}: {f.message}  → {f.snippet}"
            for f in findings
        )
        super().__init__(msg)
