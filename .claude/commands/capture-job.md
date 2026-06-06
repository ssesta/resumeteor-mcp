---
description: Capture a job posting completely — structured fetch, then screenshot→LLM extraction, validated for completeness.
argument-hint: <jobs/folder>
---

Capture (or repair) the posting for the job folder: `$ARGUMENTS`

A capture is only **complete** when `$ARGUMENTS/job-description.md` contains all three of:
1. **What the role is** — a real description / "about the role".
2. **What you'll do** — responsibilities / duties.
3. **What they want** — required skills, experience, and qualifications.

Anything less is **incomplete**: try another method, and if you exhaust them, leave the folder flagged incomplete — never pretend a thin or partial capture is done.

## Steps

1. **Run the structured capturer** (cheap, no tokens, high-fidelity for known ATS). Read the `url` from `$ARGUMENTS/job.yaml`, then:
   `.venv/bin/python scripts/capture_job.py <url> $ARGUMENTS`
   It tries embedded-ATS APIs (Ashby `ashby_jid`, Greenhouse `gh_jid`), then `requests`, then headless Playwright — which also saves a full-page `job-screenshot.png`. It writes `job-description.md`, runs a completeness check, and reports `status` = `captured` (complete) / `incomplete` / `needs_manual_paste`.

2. **Verify completeness yourself.** Read `$ARGUMENTS/job-description.md`. If it genuinely has all three required elements, you're done — go to step 5 (Complete). The heuristic can be fooled both ways, so trust your own read over the reported status.

3. **If incomplete or failed → universal screenshot→LLM extraction (this is the durable fallback — it's you, not a new parser).** The page is JS-heavy, embeds an unknown ATS, or scraped to marketing/benefits noise. Rather than adding yet another per-provider handler:
   - **Read `$ARGUMENTS/job-screenshot.png`** (you can read the full-page screenshot image directly) and **`$ARGUMENTS/job-source.html`** if present.
   - Reconstruct a clean `job-description.md` from them: role description, responsibilities/duties, and requirements/qualifications (skills & experience), plus comp/location if shown. Keep the `<!-- captured … -->` provenance line and the source URL; drop any `> ⚠️ INCOMPLETE CAPTURE` banner once you've filled the gaps. **Transcribe what's on the page — never invent.**
   - Re-check the three required elements.

4. **If the screenshot and HTML are also insufficient** (login wall, blank/partial render):
   - Re-run step 1 once (Playwright sometimes needs a second pass), or capture a more specific URL — e.g., the ATS-hosted page (`jobs.ashbyhq.com/<org>/<id>`, `boards.greenhouse.io/<token>/jobs/<id>`) instead of a marketing embed.
   - Otherwise ask the user to open the URL in Chrome (where they're logged in) and use the **Claude Chrome extension** to grab the posting, or paste it into `job-description.md`.

5. **End in exactly one state, honestly:**
   - **Complete** — `job-description.md` has all three elements and no incomplete banner. Tell the user it's ready for `/tailor jobs/<folder>`.
   - **Incomplete (methods exhausted)** — keep a `> ⚠️ INCOMPLETE CAPTURE — missing: …` banner at the top of `job-description.md` naming what's still missing, and tell the user plainly what you tried. The UI shows the folder flagged incomplete and `/tailor` will refuse a stub.

## Rules
- Never invent or guess posting content — transcribe from the screenshot / HTML / page only.
- "Complete" means all three elements are present. A benefits-and-perks blob, a title-only page, or a login wall is **incomplete** — say so.
- Prefer the cheap structured path first; only spend tokens on screenshot→LLM extraction when validation says you need to.
