---
description: Produce a carefully tailored, honest resume source for a given job folder.
argument-hint: <jobs/folder>
---

Tailor a resume for the job in: `$ARGUMENTS`

## Bulk mode (`-all`, `-refreshall`)

If `$ARGUMENTS` is `-all` or `-refreshall`, this is a batch run over many jobs:
- **`-all`** — tailor every job that doesn't have a resume yet. Get the list with
  `.venv/bin/python scripts/tailor_targets.py --mode all` (job folders with a usable description, no `resume-source.yaml`, not yet applied).
- **`-refreshall`** — re-tailor every job you haven't applied to. Get the list with
  `.venv/bin/python scripts/tailor_targets.py --mode refresh` (all not-applied job folders with a usable description).

For each folder the script prints, run the full single-job procedure below (Steps 1–6), one at a time. Skip — with a one-line note — any folder whose description is flagged incomplete (don't tailor a partial posting). When done, summarize: which were tailored, which were skipped and why, and which now have follow-up questions to answer. Then stop — don't also run the single-job flow.

For a normal single-job run, `$ARGUMENTS` is a `jobs/<folder>` path — continue below.

---

The goal is a resume that is a **viable, competitive application for this specific role** while remaining **strictly honest** and still recognizably *this candidate* — not a generic mirror of the posting. Tailoring means **selecting, reordering, reframing, and sharpening** real experience. It never means inflating it. Over-fitting — stretching past experience to look like a point-by-point match — is the failure mode this skill exists to prevent: it gets exposed in interviews, it reads as generic, and modern screening penalizes it. But the opposite failure matters too: stripping real, defensible experience to satisfy a literal-minded check makes the candidate look weaker than they are. Aim for the honest *and* competitive middle.

## Principles (read before tailoring)

These encode how a strong resume actually gets read and what gets it rejected.

1. **Calibrate every claim to evidence.** Before writing any bullet, grade the underlying evidence from the dossier:
   - **Direct** — the candidate demonstrably did this. State it plainly and lead with it.
   - **Adjacent** — closely related or transferable. Frame it honestly as what it actually was ("applied X to Y"), never as the exact requirement.
   - **Exposure** — familiarity, not ownership. Mention modestly, if at all. Never phrase as expertise or leadership.
   - **None** — no evidence. Do not claim it. Record it as a gap.

   The verb, scope, and implied seniority of every bullet must match its grade. "Led" ≠ "contributed to" ≠ "was exposed to." Whenever there is doubt about *strength*, choose the more modest true phrasing — but reasonable reframing of real experience in the posting's vocabulary is fine and expected (see Principle 5 and the calibration note in Step 4).

2. **Keep the real candidate.** Tailor by emphasis, not amputation. Retain genuinely strong experience even when it isn't a literal requirement — it signals seniority, range, judgment, and trajectory, and it differentiates the candidate. A resume trimmed down to only the posting's bullets reads as generic and *under-levels* a senior candidate. Cut what is irrelevant or weak; keep what makes this person distinct.

3. **Lead with strength.** Recruiters scan in seconds, reading the first few words of each bullet down the left margin and the top of the page first. Put the strongest, most role-relevant evidence first — in the summary, in role/bullet ordering, and in the opening words of each bullet.

4. **Accomplishments over responsibilities; quantify honestly.** Prefer "action + scope + measurable result" over duty descriptions. Use real numbers from the dossier. If an exact figure isn't recorded, an honest scope/frequency/range is acceptable ("across 3 teams," "weekly cadence") — never invent a precise metric.

5. **Match language honestly, don't parrot.** Mirror the posting's vocabulary only where the candidate genuinely has the experience, roughly 1–3 times. Honest equivalents are fine — modern screening matches "led cross-functional projects" to "managed cross-functional teams" semantically, so you do not need to copy exact phrasing, and keyword-stuffing is detected and counts against the candidate.

6. **Differentiate, don't converge.** Two candidates who both rewrote their resumes to mirror this posting look identical. The edge comes from real, specific, well-evidenced accomplishments — surface those rather than chasing keyword coverage.

## Inputs
- `kitchen-sink/profile.yaml` — the dossier: canonical content. **Tailoring may select, reorder, and reframe items from this. It may not invent new facts, and may not upgrade the strength of a claim beyond what the source fairly supports.**
- `kitchen-sink/narrative.md` — long-form material; read it in full for the context, evidence, and metrics that justify honest reframing.
- `$ARGUMENTS/job-description.md` — the posting.
- `$ARGUMENTS/job.yaml` — metadata.
- `$ARGUMENTS/custom-content.md` — **if it exists and is non-empty**, job-specific material the user added through the UX. Treat it as authoritative new content the user wants surfaced. Weave it in naturally; if it duplicates something in the dossier, prefer the more job-relevant phrasing.

## Steps

1. **Read** the dossier (`profile.yaml` *and* `narrative.md`) and the job description in full. If `job-description.md` looks empty, malformed, like a paste stub ("paste the job description here"), or carries an "⚠️ INCOMPLETE CAPTURE" banner, STOP and tell the user to finish capturing the posting first (`/capture-job jobs/<folder>`) — don't tailor against a partial posting.

2. **Analyze** the role and write `$ARGUMENTS/analysis.md` containing:
   - **Must-haves** the posting names explicitly.
   - **Nice-to-haves** / preferred qualifications.
   - **Implicit signals** — seniority/altitude, domain, team shape, culture cues.
   - **Match map** — for each must-have, the best dossier evidence *and its grade* (Direct / Adjacent / Exposure / None). This grade governs how strongly the corresponding bullet may be phrased.
   - **Distinctive strengths beyond the posting** — real, strong experience that isn't a literal requirement but signals seniority, range, or differentiation, and should survive into the resume (Principle 2).
   - **Gaps** — must-haves that grade Exposure/None. For each, an honest recommendation: reframe an adjacent strength, surface it honestly as a smaller point, omit, or ask the user for new content. Never recommend fabricating.

3. **Tailor.** Write `$ARGUMENTS/resume-source.yaml` — same schema as `profile.yaml` — applying the Principles above:
   - Select the relevant bullets per role (set `general: true` on selected ones, omit the rest), but keep enough distinctive non-requirement strength to represent the real candidate (Principle 2).
   - Reorder roles / skills / bullets to lead with the strongest, most relevant evidence (Principle 3).
   - Rewrite the `summary` (2–4 sentences) to position the candidate for this role, leading with the must-haves they answer **Directly**. No generic filler.
   - Rewrite bullets to surface relevant language and honest metrics (Principles 4–5), with each bullet's strength matched to its evidence grade (Principle 1).
   - Drop sections that add nothing for this role.

4. **Honesty critique loop — the only thing that loops.** Tailoring is a backend process; spend the turns to get honesty right. Do **not** grade your own draft — each round, launch an **independent critic subagent** (Task tool, fresh context).

   Give the critic only these paths: `$ARGUMENTS/resume-source.yaml` (the draft), `$ARGUMENTS/job-description.md`, `kitchen-sink/profile.yaml`, `kitchen-sink/narrative.md`, and `$ARGUMENTS/custom-content.md` (if present) — **not** your tailoring rationale. Have it go claim by claim and sort every observation into exactly one bucket:

   - **HONESTY VIOLATION (must-fix — this is what loops).** A fabricated fact (employer, title, dates, degree, certification, metric, number, or team size that appears nowhere in the dossier), or a material overclaim (a title/function the candidate never held, stated as fact; ownership asserted where the dossier shows only contribution; expertise asserted where it shows only exposure; a precise figure with no basis). Quote it; name the fix.
   - **CONFIRM / ENRICH (do NOT strip — becomes a question).** A claim that is a *plausible, honest representation* of this candidate but isn't yet explicitly evidenced in the dossier (a reasonable reframing or honest equivalent). Keep a measured version on the resume; record it for Step 5 so the user can confirm it and enrich the dossier.
   - **POSITIONING / WORDING (advisory — does NOT loop).** Ordering, lead-with-strength, density, parallelism, polish. Noted for the single judgment pass in 4b, not for looping.
   - **GENUINE GAP (never fabricate — becomes a question).** A must-have with no supporting evidence at all. Record for Step 5.

   **Calibration — do not over-compensate.** Honest equivalents and reasonable reframing of real experience are allowed even when the exact term isn't in the dossier, as long as someone reading the dossier would find the claim a fair representation. Reserve HONESTY VIOLATION for genuine fabrication or material inflation — *not* for vocabulary choices. When a borderline claim is plausibly true for this candidate, it is CONFIRM/ENRICH (keep it + ask), not a violation (strip it). Stripping real, defensible experience to satisfy a literal check is itself a failure.

   The critic ends with a one-line verdict: **PASS** (zero HONESTY VIOLATIONS) or **REVISE**.

   Loop on HONESTY VIOLATIONS only: apply the fixes to `resume-source.yaml`, then launch a *fresh* critic. Repeat until **PASS** or until 3 rounds have run. POSITIONING and CONFIRM/ENRICH items never trigger another round. If round 3 still shows violations, STOP and report them honestly rather than papering over them.

4b. **Final judgment pass (runs once — no loop).** With honesty clean, make your *own* call on the POSITIONING / WORDING advice: apply what genuinely improves honest competitiveness (lead-with-strength, ordering, trimming), ignore the rest. Do not re-litigate or spawn another critic — subjective positioning is your judgment to settle, not grounds to keep looping.

5. **Capture the gaps as background questions.** Write `$ARGUMENTS/background-questions.yaml` from the analysis gaps, the critic's GENUINE GAPS, and its CONFIRM/ENRICH items (plausible claims kept on the resume but not yet evidenced in the dossier). These become the user's prompts in the UI to enrich the dossier so the *next* tailoring is stronger. Schema:

   ```yaml
   generated: "<YYYY-MM-DD>"
   company: "<company>"
   role: "<role>"
   questions:
     - id: <kebab-case>
       theme: "<short label, e.g. Change management>"
       priority: must-have | nice-to-have | differentiator
       why: "<why it matters for THIS role — paraphrase the posting>"
       dossier_gap: "<what's missing, or the claim kept that isn't yet evidenced>"
       attach_to: "<employer/role the evidence would strengthen, if known>"
       prompt: "<a specific elaboration question — ask for situation, action, result, numbers, names, dates>"
       answer: ""
   ```

   Rules: one question per genuine gap or confirm/enrich item; lead with must-haves; cap at ~6–8 so it doesn't overwhelm. Every `prompt` must be answerable and, once answered, directly usable as honest evidence (ask for specifics, not yes/no). Do NOT ask about anything already well-evidenced in the dossier. Always end with one open-ended catch-all (`id: additional-accomplishments`). Leave every `answer` blank — the user fills them in the UI, and "Save to dossier" appends answered items to `kitchen-sink/narrative.md` for future tailoring.

6. **Report** to the user:
   - One paragraph on the tailoring choices and how the resume is positioned for this role.
   - The critic's final verdict and how many rounds it took; note any HONESTY VIOLATIONS that remain (should be none after PASS), and the positioning calls you made in 4b.
   - The gaps captured in `background-questions.yaml` — and a nudge to answer them in the UI's **Background questions** panel and click **Save to dossier**, so the next tailoring is stronger.
   - Next step: `.venv/bin/python scripts/build_resume.py $ARGUMENTS`

## Hard rules
- Never invent **or materially inflate**: no fabricated employers, titles, dates, metrics, degrees, certifications, or technologies — and no inflating a contribution into ownership, a familiarity into expertise, or an estimate into a precise figure.
- Every claim must be a **fair representation** of something in `profile.yaml`, `narrative.md`, or a non-empty `custom-content.md`. Reasonable reframing and honest equivalents are fine; invented facts and material inflation are not. When a claim is plausibly true but not yet evidenced, keep a measured version *and* raise it as a background question — don't fabricate, and don't strip real experience to satisfy a literal check.
- If the dossier lacks any evidence for a must-have, flag it as a gap; do not fake it.
- Tailor by selection, ordering, and honest reframing — never by exaggeration, and never by shrinking the candidate down to the posting.
- Keep the resume to roughly two pages worth of content (about 600–800 words across bullets).
