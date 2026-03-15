"""Auto-initialize .terminal_hub/ directory structure and detect cwd and GitHub repo."""
import os
import re
import subprocess
from pathlib import Path


def init_workspace(root: Path) -> None:
    """Create .terminal_hub/ structure if it does not exist. Idempotent."""
    (root / ".terminal_hub" / "issues").mkdir(parents=True, exist_ok=True)


def detect_repo(root: Path) -> str | None:
    """Return 'owner/repo' from GITHUB_REPO env var or git remote origin.

    Returns None if neither is available.
    """
    if repo := os.environ.get("GITHUB_REPO"):
        return repo

    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None

    # Parse both SSH (git@github.com:owner/repo.git) and HTTPS formats
    match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", remote)
    return match.group(1) if match else None
