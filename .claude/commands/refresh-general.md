---
description: Rebuild the general-purpose resume from the kitchen sink.
---

1. Read `kitchen-sink/profile.yaml`. If the summary or any required identity field is still `TODO`, tell the user before rebuilding.
2. Run `.venv/bin/python scripts/build_resume.py general`.
3. Report the output path and the rough length (count experience bullets to estimate page count).
4. If the kitchen sink has changed substantially since the last build, suggest a `/critique` pass against the user's most common target role.
