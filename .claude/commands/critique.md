---
description: Critique a tailored resume against the job description.
argument-hint: <jobs/folder>
---

Critique the resume in `$ARGUMENTS/resume-source.yaml` against `$ARGUMENTS/job-description.md`.

Address:

1. **Must-have coverage**. For each must-have from the posting, is there a bullet/skill that maps to it? Score 0–3.
2. **Lead with strength**. Does the summary and first role's first bullet hit the strongest signal for this role?
3. **Specificity**. Are bullets concrete (verb + scope + metric) or generic? Call out any that read as fluff.
4. **Language match**. Does the resume use the posting's vocabulary where honest? (Don't suggest keyword-stuffing — only where the user has genuine experience the kitchen sink supports.)
5. **Length and density**. Estimated page count. Sections that should be trimmed.
6. **Risks**. Anything that could read as a red flag for this specific role (gaps, mismatched seniority, missing keywords).

End with: a **prioritized** list of concrete edits to make to `resume-source.yaml`. Don't make the edits — let the user decide.
