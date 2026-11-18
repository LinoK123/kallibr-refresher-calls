"""Kallibr refresher push hook for the nightly job (designated PC only).

Copy this file into the KallibrAgent folder. axc_nightly.pyw calls run_if_enabled(HERE) after a
successful sync. It does nothing unless refresher_push.json sits next to it:

    {"repo": "C:\\Users\\<you>\\Documents\\Claude\\Claude Code\\kallibr-refresher-calls"}

Never put refresher_push.json in a setup package: it is what makes a PC the designated one.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SETTING = "refresher_push.json"


def run_if_enabled(here: Path) -> int | None:
    """Run the refresher push if this PC is set up for it. None when not enabled, else its exit code."""
    cfg = Path(here) / SETTING
    if not cfg.exists():
        return None
    try:
        repo = Path(json.loads(cfg.read_text(encoding="utf-8"))["repo"])
    except Exception as e:
        print(f"Refresher push: can't read {SETTING}: {e}")
        return 1
    script = repo / "push" / "refresher_push.py"
    if not script.exists():
        print(f"Refresher push: {script} not found (check 'repo' in {SETTING}).")
        return 1
    try:
        p = subprocess.run([sys.executable, str(script)], cwd=str(script.parent), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=3600,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        print("Refresher push: timed out after an hour.")
        return 1
    # Printed here so it lands wherever the nightly job sends its output (sync.log).
    if p.stdout:
        print(p.stdout, end="" if p.stdout.endswith("\n") else "\n")
    if p.stderr:
        print(p.stderr, end="" if p.stderr.endswith("\n") else "\n")
    return p.returncode
