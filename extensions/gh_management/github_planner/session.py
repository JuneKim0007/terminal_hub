"""Session repo confirmation and MCP-layer auth wrappers for github_planner."""
# stdlib
import json
from pathlib import Path

# internal
from extensions.gh_management.github_planner.auth import get_auth_options


def _pkg():
    """Return the github_planner package module so patches applied by tests are respected."""
    import sys
    return sys.modules['extensions.gh_management.github_planner']

# Runtime session cache — keyed by workspace root str so switching directories re-prompts correctly.
_SESSION_REPO_CONFIRMED: dict[str, str] = {}  # root_str -> confirmed "owner/repo"


def _detect_project_name(root: Path) -> str | None:
    """Return the project name from pyproject.toml or package.json, or None."""
    try:
        import tomllib  # 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-reattr]
        except ImportError:
            tomllib = None  # type: ignore[assignment]

    pyproject = root / "pyproject.toml"
    if tomllib and pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            return data.get("project", {}).get("name") or data.get("tool", {}).get("poetry", {}).get("name")
        except Exception:
            pass

    pkg = root / "package.json"
    if pkg.exists():
        try:
            return json.loads(pkg.read_text(encoding="utf-8")).get("name")
        except Exception:
            pass
    return None


def _do_confirm_session_repo(force: bool = False) -> dict:
    """Return the confirmed repo for this session, or prompt data if not yet confirmed."""
    _p = _pkg()

    root = _p.get_workspace_root()
    root_str = str(root)
    repo = _p.read_env(root).get("GITHUB_REPO", "")

    if not repo:
        return {"confirmed": False, "repo": None,
                "_display": "⚠️ No GITHUB_REPO configured. Run /th:gh-plan-setup to connect a repo."}

    # Already confirmed this session — check for project switch
    if not force and root_str in _SESSION_REPO_CONFIRMED:
        confirmed_repo = _SESSION_REPO_CONFIRMED[root_str]
        if confirmed_repo == repo:
            return {"confirmed": True, "repo": repo,
                    "_display": f"✓ Working on `{repo}` (confirmed this session)"}
        # Repo changed since confirmation (env var updated) — re-confirm
        del _SESSION_REPO_CONFIRMED[root_str]

    # Not yet confirmed — return prompt data for Claude to display
    project_name = _detect_project_name(root)
    repo_slug = repo.split("/")[-1] if "/" in repo else repo
    match_hint = f" (matches project name `{project_name}`)" if project_name and project_name == repo_slug else ""
    return {
        "confirmed": False,
        "repo": repo,
        "project_name": project_name,
        "_display": (
            f"❓ **Working repo:** `{repo}`{match_hint}\n"
            f"Is this the repo you want to work with? *(yes / change)*"
        ),
    }


def _do_set_session_repo(repo: str) -> dict:
    """Confirm and lock the session repo."""
    root = _pkg().get_workspace_root()
    _SESSION_REPO_CONFIRMED[str(root)] = repo
    return {"confirmed": True, "repo": repo,
            "_display": f"✅ Session locked to `{repo}`"}


def _do_clear_session_repo() -> dict:
    """Clear session repo confirmation (called by unload)."""
    root = _pkg().get_workspace_root()
    root_str = str(root)
    was_confirmed = root_str in _SESSION_REPO_CONFIRMED
    _SESSION_REPO_CONFIRMED.pop(root_str, None)
    return {"cleared": was_confirmed}


# ── Guidance URI constant needed for auth wrappers ────────────────────────────
_G_AUTH = "terminal-hub://workflow/auth"


def _do_check_auth() -> dict:
    _p = _pkg()
    token, source = _p.resolve_token()
    if token:
        return {
            "authenticated": True,
            "source": source.value,
            "message": f"Authenticated via {source.value.replace('_', ' ')}.",
        }
    return {
        "authenticated": False,
        "message": "No GitHub authentication found.",
        "options": get_auth_options(),
        "_guidance": _G_AUTH,
    }


def _do_verify_auth() -> dict:
    _p = _pkg()
    success, message = _p.verify_gh_cli_auth()
    if success:
        return {"authenticated": True, "source": "gh_cli", "message": message}
    return {
        "authenticated": False,
        "message": message,
        "options": get_auth_options(),
        "_guidance": _G_AUTH,
    }
