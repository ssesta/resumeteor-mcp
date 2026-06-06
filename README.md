# Resumeteor

Tailor résumés to each job **honestly**, using the AI subscription you already
have. The reasoning runs inside your MCP-capable chat app (Claude Desktop,
Claude Code, Cursor, VS Code) — **no API key, no per-use cost.** A small local
MCP server manages your files, captures job postings, and builds the
Word/PDF/HTML documents. Your data never leaves your machine.

## Install

See **[INSTALL.md](INSTALL.md)** — a ~2-minute, copy-paste setup.

## How it works

- The **MCP server** (`resumeteor_mcp/`) exposes tools (dossier, jobs, capture,
  build) and prompts (`tailor`, `critique`) to your chat client.
- Your client's model does the tailoring and critique **on your subscription**;
  the server only does deterministic work — file I/O, job capture, completeness
  validation, and rendering (`scripts/`).
- Your **dossier** — a "kitchen sink" of everything you've done — lives locally
  (default `~/Resumeteor`). Tailoring selects and reframes from it and never
  invents facts.

## Honesty by design

Tailoring calibrates every claim to your dossier, refuses to fabricate
employers/titles/metrics, and surfaces gaps as **background questions** you
answer to enrich the dossier — so each résumé gets stronger over time.

## Develop

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

See **[SHARING.md](SHARING.md)** for the machinery-vs-dossier split.

## License

MIT — see [LICENSE](LICENSE).
