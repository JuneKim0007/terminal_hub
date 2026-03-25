"""Setup helpers — workspace root, GitHub client factory, repo cache, guidance URIs."""
# stdlib
import sys
from pathlib import Path

# internal
from extensions.gh_management.github_planner.client import GitHubClient
from terminal_hub.workspace import resolve_workspace_root


def _pkg():
    """Return the github_planner package module so patches applied by tests are respected."""
    return sys.modules['extensions.gh_management.github_planner']

# ── Guidance URIs ─────────────────────────────────────────────────────────────
_G_INIT    = "terminal-hub://workflow/init"
_G_ISSUE   = "terminal-hub://workflow/issue"
_G_CONTEXT = "terminal-hub://workflow/context"
_G_AUTH    = "terminal-hub://workflow/auth"

_BUILTIN_COMMANDS = ["create.md", "gh-plan-setup.md", "gh-plan-auth.md", "context.md"]

_PLUGIN_DIR = Path(__file__).parent
_COMMANDS_DIR = _PLUGIN_DIR / "commands"

# Per-root repo string cache — avoids re-reading hub_agents/.env on every call (#90)
_REPO_CACHE: dict[str, str | None] = {}


def _load_agent(name: str) -> str:
    path = _COMMANDS_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def get_workspace_root() -> Path:
    from terminal_hub.workspace import resolve_workspace_root
    return resolve_workspace_root()


def ensure_initialized(root: Path) -> dict | None:
    """Return a needs_init response if hub_agents/ is absent, else None."""
    if not (root / "hub_agents").exists():
        return {
            "status": "needs_init",
            "message": (
                "This project hasn't been set up with terminal-hub yet. "
                "Ask the user: would they like GitHub integration? If yes, what is their repo (owner/repo format)? "
                "Then call setup_workspace to initialise."
            ),
            "_guidance": _G_INIT,
        }
    return None


def get_github_client() -> tuple[GitHubClient | None, str]:
    """Return (client, error_message). Client is None if auth unavailable."""
    _p = _pkg()
    token, source = _p.resolve_token()
    if token is None:
        return None, source.suggestion()

    root = get_workspace_root()
    root_key = str(root)
    # Cache detect_repo per root — avoids re-reading hub_agents/.env on every call (#90)
    if root_key not in _REPO_CACHE:
        _REPO_CACHE[root_key] = _p.detect_repo(root)
    repo = _REPO_CACHE[root_key]
    if not repo:
        return None, (
            "No GitHub repo configured for this project. "
            "Call setup_workspace with github_repo='owner/repo' to set one."
        )

    return GitHubClient(token=token, repo=repo), ""


def _invalidate_repo_cache() -> None:
    """Clear repo cache. Call after setup_workspace changes the env."""
    _REPO_CACHE.clear()
