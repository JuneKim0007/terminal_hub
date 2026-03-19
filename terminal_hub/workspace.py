"""Workspace root detection and initialisation helpers."""
import os
import re
import subprocess
from pathlib import Path


_ACTIVE_PROJECT_ROOT: Path | None = None


def _cwd() -> Path:
    """Isolated so tests can patch it cleanly."""
    return Path.cwd()


def set_active_project_root(path: str | Path) -> None:
    """Set the active project root for this session (called from Claude's cwd)."""
    global _ACTIVE_PROJECT_ROOT
    _ACTIVE_PROJECT_ROOT = Path(path).resolve()


def is_valid_project(path: Path) -> bool:
    """True if the directory looks like a project root."""
    return (path / ".git").exists() or (path / "hub_agents").exists()


def resolve_workspace_root() -> Path:
    """Return the workspace root.

    Order:
      1. Explicitly set via set_active_project_root() (Claude passes its cwd)
      2. PROJECT_ROOT env var (test injection)
      3. cwd fallback
    """
    if _ACTIVE_PROJECT_ROOT is not None:
        return _ACTIVE_PROJECT_ROOT
    if root := os.environ.get("PROJECT_ROOT"):
        return Path(root)
    return _cwd()


def init_workspace(root: Path) -> None:
    """Create hub_agents/ structure if it does not exist. Idempotent."""
    (root / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)


def detect_repo(root: Path) -> str | None:
    """Return 'owner/repo' from hub_agents/.env, GITHUB_REPO env var, or git remote origin.

    Returns None if none are available.
    """
    from terminal_hub.env_store import read_env
    if repo := read_env(root).get("GITHUB_REPO"):
        return repo

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
