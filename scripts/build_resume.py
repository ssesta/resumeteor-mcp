#!/usr/bin/env python3
"""Build a resume .docx from the kitchen sink (+ optional per-job overrides).

Usage:
    python scripts/build_resume.py general
    python scripts/build_resume.py jobs/2026-05-16__Acme__StaffEng
    python scripts/build_resume.py jobs/2026-05-16__Acme__StaffEng --output custom.docx
"""

from __future__ import annotations

import argparse
import os
import sys
from copy import deepcopy
from pathlib import Path

import yaml

_DEFAULT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_DEFAULT_ROOT / "scripts"))

from render import render_all  # noqa: E402


def _root() -> Path:
    return Path(os.environ.get("JOBSEARCH_ROOT", _DEFAULT_ROOT))


def _kitchen_sink(root: Path | None = None) -> Path:
    return (root or _root()) / "kitchen-sink" / "profile.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Override wins. Lists in override replace lists in base wholesale."""
    out = deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def build_general(output: Path | None = None, root: Path | None = None) -> dict:
    """Returns dict {docx, html, pdf} of paths."""
    root = root or _root()
    ks = _kitchen_sink(root)
    profile = _load_yaml(ks)
    if not profile:
        raise SystemExit(f"Kitchen sink not found or empty: {ks}")
    target = output or (root / "general-resume" / "general-resume.docx")
    return render_all(profile, target)


def build_job(job_dir: Path, output: Path | None = None, root: Path | None = None) -> dict:
    root = root or _root()
    if not job_dir.is_dir():
        raise SystemExit(f"Not a directory: {job_dir}")
    profile = _load_yaml(_kitchen_sink(root))
    overrides_path = job_dir / "overrides.yaml"
    overrides = _load_yaml(overrides_path)
    merged = _deep_merge(profile, overrides) if overrides else profile

    # If a per-job resume-source.yaml exists (Claude tailoring output), prefer it wholesale.
    tailored_path = job_dir / "resume-source.yaml"
    if tailored_path.exists():
        tailored = _load_yaml(tailored_path)
        if tailored:
            merged = tailored

    if not merged:
        raise SystemExit("Nothing to render — both kitchen sink and overrides are empty.")
    target = output or (job_dir / "resume.docx")
    return render_all(merged, target)


def main():
    parser = argparse.ArgumentParser(description="Render a resume .docx.")
    parser.add_argument(
        "target",
        help="Either 'general' or a path to a jobs/<folder>.",
    )
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Override output path.")
    args = parser.parse_args()

    if args.target == "general":
        paths = build_general(args.output)
    else:
        paths = build_job(Path(args.target), args.output)

    root = _root()
    for ext in ("docx", "html", "pdf"):
        p = paths[ext]
        try:
            rel = p.resolve().relative_to(root.resolve())
        except (ValueError, OSError):
            rel = p
        print(f"Wrote {rel}")


if __name__ == "__main__":
    main()
