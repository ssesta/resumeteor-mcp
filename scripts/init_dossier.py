#!/usr/bin/env python3
"""Seed a fresh dossier from the templates so a new user can start.

Copies templates/kitchen-sink/{profile.yaml,narrative.md} into kitchen-sink/
(only if missing — never overwrites real data) and creates the working
directories the workflow expects.

Usage:
    python scripts/init_dossier.py
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def _root() -> Path:
    return Path(os.environ.get("JOBSEARCH_ROOT", _DEFAULT_ROOT))


def init_dossier(root: Path | None = None) -> list[str]:
    """Idempotent: safe to run repeatedly; never overwrites existing files.
    Returns a list of human-readable actions taken."""
    root = root or _root()
    templates = root / "templates" / "kitchen-sink"
    actions: list[str] = []

    for rel in ("kitchen-sink", "kitchen-sink/linkedin",
                "kitchen-sink/attachments", "jobs", "general-resume"):
        d = root / rel
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            actions.append(f"created {rel}/")

    for name in ("profile.yaml", "narrative.md"):
        dest = root / "kitchen-sink" / name
        src = templates / name
        if dest.exists():
            actions.append(f"kept existing kitchen-sink/{name} (not overwritten)")
        elif src.exists():
            shutil.copyfile(src, dest)
            actions.append(f"seeded kitchen-sink/{name} from template")
        else:
            actions.append(f"WARNING: template missing: {src}")

    return actions


def main():
    root = _root()
    print(f"Dossier init in {root}:")
    for a in init_dossier(root):
        print(f"  - {a}")
    print("\nNext: fill in kitchen-sink/profile.yaml and narrative.md, then run")
    print("  .venv/bin/python scripts/build_resume.py general")


if __name__ == "__main__":
    main()
