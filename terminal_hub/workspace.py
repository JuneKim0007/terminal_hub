"""Auto-initialize .terminal_hub/ directory structure and detect cwd and GitHub repo."""
import os
import re
import subprocess
from pathlib import Path


def _cwd() -> Path:
    """Isolated so tests can patch it cleanly."""
    return Path.cwd()


def is_valid_project(path: Path) -> bool:
    """True if the directory looks like a project root."""
    return (path / ".git").exists() or (path / ".terminal_hub").exists()


def resolve_workspace_root() -> Path | None:
    """Return the workspace root using a prioritised resolution chain.

    Order:
      1. PROJECT_ROOT env var (explicit override)
      2. PROJECT_ROOT stored in .terminal_hub/.env in cwd
      3. cwd itself, if it looks like a project
      4. None — caller must ask the user
    """
    # 1. Explicit env var
    if root := os.environ.get("PROJECT_ROOT"):
        return Path(root)

    cwd = _cwd()

    # 2. .terminal_hub/.env in cwd
    from terminal_hub.env_store import read_env
    env = read_env(cwd)
    if root := env.get("PROJECT_ROOT"):
        return Path(root)

    # 3. Validate cwd
    if is_valid_project(cwd):
        return cwd

    return None


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
