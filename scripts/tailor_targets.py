#!/usr/bin/env python3
"""List job folders eligible for a bulk /tailor run.

Used by the /tailor skill for `-all` and `-refreshall`:
  --mode all      jobs with a usable description but no resume-source.yaml yet
  --mode refresh  all not-yet-applied jobs with a usable description (re-tailor)

Applied jobs (explicit state submitted/interviewing/closed, or applied: true in
job.yaml) are always excluded. Prints one `jobs/<folder>` path per line.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

_DEFAULT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_DEFAULT_ROOT / "scripts"))

from job_validation import validate_job_file  # noqa: E402

APPLIED_STATES = {"submitted", "interviewing", "closed"}


def _root() -> Path:
    return Path(os.environ.get("JOBSEARCH_ROOT", _DEFAULT_ROOT))


def targets(mode: str, root: Path | None = None) -> list[str]:
    root = root or _root()
    jobs = root / "jobs"
    out: list[str] = []
    if not jobs.exists():
        return out
    for d in sorted(jobs.iterdir()):
        if not d.is_dir():
            continue
        job = {}
        jy = d / "job.yaml"
        if jy.exists():
            try:
                job = yaml.safe_load(jy.read_text()) or {}
            except yaml.YAMLError:
                job = {}
        # Skip jobs already applied to.
        if (job.get("state") or "") in APPLIED_STATES or job.get("applied"):
            continue
        # Need a usable (present) description to tailor against.
        if not validate_job_file(d / "job-description.md").get("present"):
            continue
        if mode == "all" and (d / "resume-source.yaml").exists():
            continue  # -all only targets jobs without a tailored resume yet
        out.append(str(d.relative_to(root)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["all", "refresh"], required=True)
    args = ap.parse_args()
    for p in targets(args.mode):
        print(p)


if __name__ == "__main__":
    main()
