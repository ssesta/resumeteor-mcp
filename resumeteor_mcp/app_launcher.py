"""Launch the Resumeteor local web app (the dashboard).

`resumeteor-app` runs the Flask UI against your dossier — `~/Resumeteor` by
default, the SAME folder the MCP server uses — so the app and your AI work on
shared data. Manage jobs, build your dossier, review/build résumés, track
progress in the browser; your AI (via the MCP) does the tailoring.

Run:  resumeteor-app        (opens http://127.0.0.1:5050)
Data: ~/Resumeteor          (override with RESUMETEOR_HOME)
Port: 5050                  (override with PORT)
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import webbrowser
from pathlib import Path

_PKG = Path(__file__).resolve().parent
_BUNDLED = _PKG / "_bundled"
_ROOT = _BUNDLED if _BUNDLED.exists() else _PKG.parent   # installed wheel vs. repo


def _home() -> Path:
    return Path(os.environ.get("RESUMETEOR_HOME", Path.home() / "Resumeteor")).expanduser()


def _seed(home: Path) -> None:
    """Create the dossier folders + starter files on first run (never overwrites)."""
    tpl = _ROOT / "templates" / "kitchen-sink"
    for rel in ("kitchen-sink", "jobs", "general-resume"):
        (home / rel).mkdir(parents=True, exist_ok=True)
    for name in ("profile.yaml", "narrative.md"):
        dest = home / "kitchen-sink" / name
        if not dest.exists() and (tpl / name).exists():
            shutil.copyfile(tpl / name, dest)


def _make_app(home: Path):
    os.environ["JOBSEARCH_ROOT"] = str(home)
    sys.path.insert(0, str(_ROOT / "scripts"))
    sys.path.insert(0, str(_ROOT / "ui"))
    from app import create_app  # bundled ui/app.py
    return create_app(home)


def main() -> None:
    home = _home()
    _seed(home)
    flask_app = _make_app(home)
    port = int(os.environ.get("PORT", "5050"))
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Resumeteor is running → {url}\n  Your files live in:    {home}\n"
          f"  Keep this window open while you use it. Press Ctrl-C to stop.\n")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    flask_app.run(host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
