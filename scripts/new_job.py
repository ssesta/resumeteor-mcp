#!/usr/bin/env python3
"""Create a new job application folder and capture the posting.

Usage:
    python scripts/new_job.py "https://example.com/jobs/123"
    python scripts/new_job.py "https://..." --company Acme --role "Staff Engineer"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml

_DEFAULT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_DEFAULT_ROOT / "scripts"))

from capture_job import capture  # noqa: E402


def _root() -> Path:
    return Path(os.environ.get("JOBSEARCH_ROOT", _DEFAULT_ROOT))


def _jobs_dir(root: Path | None = None) -> Path:
    return (root or _root()) / "jobs"


def _slug(s: str, fallback: str = "unknown") -> str:
    s = (s or "").strip()
    if not s:
        return fallback
    s = re.sub(r"[^A-Za-z0-9]+", "-", s)
    s = s.strip("-")
    return s or fallback


def _guess_company(url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower().removeprefix("www.")
    # Workday URLs: <company>.wd1.myworkdayjobs.com
    if host.endswith("myworkdayjobs.com"):
        return host.split(".")[0]
    # boards.greenhouse.io/<company>/jobs/...
    parts = urlparse(url).path.strip("/").split("/")
    if host.endswith("greenhouse.io") and parts:
        return parts[0]
    if host.endswith("lever.co") and parts:
        return parts[0]
    if host.endswith("ashbyhq.com") and parts:
        return parts[0]
    return host.split(".")[0]


def make_job_folder(url: str, company: str | None, role: str | None,
                    root: Path | None = None) -> Path:
    jobs_dir = _jobs_dir(root)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    company = _slug(company or _guess_company(url), fallback="unknown-co")
    role = _slug(role, fallback="unknown-role")
    name = f"{date.today().isoformat()}__{company}__{role}"
    folder = jobs_dir / name
    if folder.exists():
        i = 2
        while (jobs_dir / f"{name}-{i}").exists():
            i += 1
        folder = jobs_dir / f"{name}-{i}"
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def write_job_yaml(folder: Path, url: str, company: str | None, role: str | None):
    data = {
        "url": url,
        "company": company or "",
        "role": role or "",
        "date_added": date.today().isoformat(),
        "status": "drafting",      # drafting | submitted | interviewing | closed
        "recruiter": "",
        "comp_range": "",
        "notes": "",
    }
    (folder / "job.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--company", default=None)
    parser.add_argument("--role", default=None)
    parser.add_argument("--no-capture", action="store_true",
                        help="Skip automated capture (just scaffold the folder).")
    args = parser.parse_args()

    root = _root()
    folder = make_job_folder(args.url, args.company, args.role)
    write_job_yaml(folder, args.url, args.company, args.role)
    rel = folder.relative_to(root)
    print(f"Created {rel}")

    if args.no_capture:
        print("Skipped capture. Run `python scripts/capture_job.py <url> <folder>` when ready.")
        return

    print("Capturing job posting...")
    result = capture(args.url, folder)
    print(f"  status={result['status']} via={result['via']} words={result['words']}")

    if result["status"] != "captured":
        print()
        if result["status"] == "needs_manual_paste":
            print("⚠  Automated capture didn't yield enough content.")
        else:
            print(f"⚠  Capture looks incomplete (missing: {', '.join(result.get('missing', []))}).")
        print(f"   Run /capture-job {rel} in Claude Code to extract from the screenshot,")
        print(f"   or open the URL in Chrome (Claude extension) and paste into {rel}/job-description.md")

    print()
    print("Next:")
    print(f"  1. Verify {rel}/job-description.md")
    print(f"  2. In Claude Code: /tailor {rel}")
    print(f"  3. python scripts/build_resume.py {rel}")


if __name__ == "__main__":
    main()
