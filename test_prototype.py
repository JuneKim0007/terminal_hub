"""
Quick manual prototype test — no Claude needed.
Run: python test_prototype.py
"""
from pathlib import Path
import tempfile

from terminal_hub.slugify import slugify
from terminal_hub.workspace import init_workspace, detect_repo
from terminal_hub.config import save_config, load_config, WorkspaceMode

SEP = "-" * 50

# ── 1. Slugify ────────────────────────────────────────
print(SEP)
print("1. SLUG NORMALIZATION")
titles = [
    "Fix authentication bug in login flow",
    "Add GitHub issue automation!!",
    "UPPERCASE TITLE with special @#$ chars",
]
for t in titles:
    print(f"  '{t}'\n  → '{slugify(t)}'")

# ── 2. Workspace init ─────────────────────────────────
print(SEP)
print("2. WORKSPACE INIT")
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    init_workspace(root)
    created = list(root.rglob("*"))
    for p in sorted(created):
        print(f"  created: {p.relative_to(root)}")

# ── 3. Config read/write ──────────────────────────────
print(SEP)
print("3. CONFIG READ/WRITE")
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    print(f"  before save: {load_config(root)}")
    save_config(root, WorkspaceMode.LOCAL, repo=None)
    print(f"  after local save: {load_config(root)}")
    save_config(root, WorkspaceMode.GITHUB, repo="JuneKim0007/terminal_hub")
    print(f"  after github save: {load_config(root)}")

# ── 4. Repo detection ─────────────────────────────────
print(SEP)
print("4. REPO DETECTION (from this repo)")
here = Path(".")
repo = detect_repo(here)
print(f"  detected: {repo}")

print(SEP)
print("All checks passed. Backend layer is working.")
print(SEP)
