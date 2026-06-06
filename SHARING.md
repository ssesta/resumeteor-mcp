# Sharing & portability

This project cleanly separates **the machinery** (generic, shareable) from
**your dossier** (personal data). You can hand a fresh copy to anyone — they
point it at their own dossier and get the same workflow, which then improves for
them as they enrich their dossier.

## What's machinery (portable — no personal data)

| Path | What it is |
|---|---|
| `.claude/commands/` | The skills: `/tailor`, `/critique`, `/new-job`, `/capture-job`, `/refresh-general` |
| `scripts/` | Build / render / capture / lint / init plumbing (no LLM calls) |
| `ui/` | Local Flask management app |
| `templates/kitchen-sink/` | Starter dossier (empty schema + narrative scaffold) |
| `requirements.txt`, `README.md`, `SHARING.md` | Setup + docs |

Nothing in the machinery hardcodes a person — the skills read the dossier by
path (`kitchen-sink/...`, `jobs/<folder>/...`). So tuning a skill prompt (e.g.
`/tailor`) improves it for *every* user and is safe to copy across installs.

## What's your dossier (personal — one user's data)

| Path | What it is |
|---|---|
| `kitchen-sink/profile.yaml` | Canonical resume content |
| `kitchen-sink/narrative.md` | Long-form material; grows via the UI |
| `kitchen-sink/linkedin/`, `kitchen-sink/attachments/` | Raw source material (gitignored) |
| `jobs/<…>/` | One folder per application |
| `general-resume/` | Built general resume (artifacts gitignored) |

## Start fresh (new user)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python scripts/init_dossier.py     # seeds kitchen-sink/ from templates/ (never overwrites)
```

Then fill in `kitchen-sink/profile.yaml` and `narrative.md` (paste from your
résumé / LinkedIn export — see README "LinkedIn ingestion"), and run the UI
(`python ui/app.py`).

## Deliver a fresh copy to someone else

Ship the **machinery** and the **templates**, not your data or local config.
Exclude:

- `kitchen-sink/profile.yaml`, `kitchen-sink/narrative.md`, `kitchen-sink/linkedin/`, `kitchen-sink/attachments/`
- `jobs/`, `general-resume/`
- `.claude/settings.local.json` (your local permissions)
- `initialprompt.md`, and any personal mentions in `PLAN.md` / `DOCREVIEW.md`

One way, straight from git:

```bash
git archive --format=tar HEAD \
  ':(exclude)kitchen-sink/profile.yaml' ':(exclude)kitchen-sink/narrative.md' \
  ':(exclude)jobs/*' ':(exclude)general-resume/*' ':(exclude)initialprompt.md' \
  | tar -x -C /path/to/fresh-copy
```

The recipient runs `python scripts/init_dossier.py` to seed an empty dossier
from `templates/`, then starts adding their own history.

## The improvement loop

Each `/tailor` run writes `background-questions.yaml` for the job. Answering
those in the UI and clicking **Save to dossier** appends the answers to
`kitchen-sink/narrative.md` with provenance. The dossier gets richer, so the
next tailoring is more honest *and* more competitive — per user, automatically.
