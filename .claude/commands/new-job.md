---
description: Scaffold a job folder and capture the posting from a URL.
argument-hint: <url> [--company NAME] [--role TITLE]
---

Run the new-job scaffolder for: `$ARGUMENTS`

Steps:
1. Execute `.venv/bin/python scripts/new_job.py $ARGUMENTS`. It scaffolds the folder and runs the structured capture chain (embedded-ATS APIs → requests → Playwright + screenshot), then validates completeness and prints a `status`.
2. **If `status=captured`** and `job-description.md` genuinely has the role description, duties, and requirements, suggest `/tailor jobs/<folder>` next.
3. **If `status=incomplete` or `status=needs_manual_paste`**, the posting isn't fully captured. Continue with the `/capture-job jobs/<folder>` flow: read the saved `job-screenshot.png` + `job-source.html` and extract a complete `job-description.md` (description + duties + requirements), or escalate to Claude-in-Chrome / manual paste. Stop only when the folder is complete or you've exhausted methods and left it flagged incomplete.

Do not fetch the URL yourself with WebFetch — `new_job.py` already runs the full structured chain. When structured capture comes up short, the full-page screenshot it saved is your material for the universal extraction in `/capture-job`.
