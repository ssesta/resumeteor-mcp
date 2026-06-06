# Resumeteor — tailor résumés with the AI subscription you already pay for

Resumeteor tailors your résumé to each job **honestly** and tracks your
applications. The *thinking* (tailoring, critique) happens inside your own AI
chat app — Claude Desktop, Claude Code, Cursor, VS Code — billed to **your
existing subscription**. This small **MCP server** runs on your computer and does
the un-glamorous parts: managing your files, capturing job postings, and building
the Word/PDF documents. **No API key. No per-use cost. Your data never leaves
your machine.**

---

## 1. One-time setup (about 2 minutes)

1. **Install `uv`** (a tiny tool that runs the server for you — you won't have to
   download or update Resumeteor by hand):
   - **macOS / Linux:** paste into Terminal:
     `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - **Windows:** paste into PowerShell:
     `irm https://astral.sh/uv/install.ps1 | iex`
2. Have one MCP-capable app you already pay for. **Claude Desktop is the easiest.**

That's all — you do **not** clone a repo or install Resumeteor manually. Your
chat app launches it automatically.

---

## 2. Add Resumeteor to your app (copy-paste once)

### Claude Desktop  ⟵ easiest, recommended
Open Claude Desktop → **Settings → Developer → Edit Config** (or open the file
directly):
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Paste this (if `mcpServers` already exists, just add the `"resumeteor"` block),
then **fully quit and reopen Claude Desktop**:

```json
{
  "mcpServers": {
    "resumeteor": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/ssesta/resumeteor-mcp", "resumeteor-mcp"]
    }
  }
}
```

### Claude Code (terminal)
```bash
claude mcp add resumeteor -- uvx --from git+https://github.com/ssesta/resumeteor-mcp resumeteor-mcp
```

### Cursor / VS Code / Windsurf
Use the same JSON block in that app's MCP settings panel.

> Replace `ssesta/resumeteor-mcp` with the GitHub repo. **Once it's published to PyPI**,
> the `--from git+…` part collapses to just `"args": ["resumeteor-mcp"]`.

---

## 3. Use it — just talk to your chat app

1. **"Set up my resume dossier."** → creates a `Resumeteor` folder in your home
   directory with starter files.
2. Open that folder and fill in `kitchen-sink/profile.yaml` and `narrative.md`
   with your history (paste from your résumé / LinkedIn export). The richer this
   is, the better every tailored résumé will be.
3. **"Add this job: \<paste the posting URL\>."** → captures the description.
4. **"Tailor my résumé for that job."** → produces an honest tailored draft plus
   a few **background questions** where more detail would strengthen it.
5. Answer those questions in chat, then **"save my answers to my dossier"** — so
   the next résumé is even better.
6. **"Build the résumé."** → writes `.docx`, `.pdf`, and `.html` into the job
   folder.

---

## Good to know

- **ChatGPT:** ChatGPT's connectors currently accept only *remote* MCP servers,
  not local ones, so Resumeteor works with **Claude Desktop, Claude Code, Cursor,
  VS Code, and Windsurf**. (A hosted option for ChatGPT could be added later.)
- **Job capture + PDF** use a headless browser. Once, run:
  `uvx --from git+https://github.com/ssesta/resumeteor-mcp playwright install chromium`
  (Word `.docx` and `.html` build fine without it.)
- **Where your files live:** `~/Resumeteor` by default. Set the `RESUMETEOR_HOME`
  environment variable to choose a different folder.
- **Honesty by design:** the tailoring never invents employers, titles, metrics,
  or skills — it reframes what's true in your dossier and asks you for anything
  it can't support.
