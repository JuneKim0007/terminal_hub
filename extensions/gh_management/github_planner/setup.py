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


def _do_bootstrap_gh_plan(
    project_root: str,
    confirm_repo: bool = True,
    sync_issues: bool = True,
) -> dict:
    """Bootstrap gh-plan session: set root, confirm repo, warm milestones, sync + list issues."""
    from terminal_hub.workspace import set_active_project_root
    from extensions.gh_management.github_planner.session import _do_confirm_session_repo, _do_set_session_repo
    from extensions.gh_management.github_planner.milestones import _do_list_milestones
    from extensions.gh_management.github_planner.issues import _do_sync_github_issues, _do_list_issues

    # Set project root
    set_active_project_root(Path(project_root).resolve())
    root = get_workspace_root()

    # Confirm repo (skip if flag off or already confirmed)
    confirmed_repo = None
    repo_changed = False
    if confirm_repo:
        confirm_result = _do_confirm_session_repo(force=False)
        confirmed_repo = confirm_result.get("repo")
        repo_changed = not confirm_result.get("confirmed", False)

    # Warm milestone cache
    milestones_result = _do_list_milestones(state="open")
    milestones = milestones_result.get("milestones", [])

    # Sync + list issues
    sync_result = {"synced": 0, "skipped": 0}
    if sync_issues:
        sync_result = _do_sync_github_issues(state="open", refresh=False)

    issues_result = _do_list_issues(compact=False)
    issues = issues_result.get("issues", [])

    # Group by milestone
    by_milestone: dict = {}
    unassigned = []
    for issue in issues:
        mn = issue.get("milestone_number")
        if mn:
            by_milestone.setdefault(mn, []).append(issue)
        else:
            unassigned.append(issue)

    # Build landscape display
    lines = []
    for mn in sorted(by_milestone.keys()):
        milestone_issues = by_milestone[mn]
        m_title = next((m.get("title", f"M{mn}") for m in milestones if m.get("number") == mn), f"Milestone {mn}")
        lines.append(f"**{m_title}**")
        for iss in milestone_issues:
            label_str = ", ".join(iss.get("labels", []))
            lines.append(f"  #{iss.get('issue_number') or iss.get('slug')} {iss.get('title')} [{label_str}]")
    if unassigned:
        lines.append("**Unassigned**")
        for iss in unassigned:
            lines.append(f"  #{iss.get('issue_number') or iss.get('slug')} {iss.get('title')}")

    landscape_display = "\n".join(lines) if lines else "No open issues."

    return {
        "workspace_ready": True,
        "confirmed_repo": confirmed_repo,
        "repo_changed": repo_changed,
        "milestones": milestones,
        "sync_result": sync_result,
        "issues": issues,
        "issue_count": len(issues),
        "landscape_display": landscape_display,
        "_display": f"✅ **gh-plan ready** — {len(issues)} issues, {len(milestones)} milestones",
    }


def _do_bootstrap_new_repo(
    project_title: str,
    project_description: str,
    tech_stack: list,
    design_principles: list,
    is_private: bool = True,
    confirm_arch_changes: bool = False,
) -> dict:
    """Create a new GitHub repo and fully bootstrap the workspace in one call."""
    from extensions.gh_management.github_planner.project_docs import _do_update_project_description, _do_save_project_docs
    from extensions.gh_management.github_planner.labels import _do_list_repo_labels
    from extensions.gh_management.github_planner.milestones import _do_list_milestones
    from extensions.gh_management.github_planner.workspace_tools import (
        _do_create_github_repo, _do_set_preference
    )
    from extensions.gh_management.github_planner.session import _do_set_session_repo

    root = get_workspace_root()

    # Save project description
    _do_update_project_description(
        title=project_title,
        description=project_description,
        notes=f"Tech stack: {', '.join(tech_stack)}",
    )

    # Create GitHub repo
    repo_result = _do_create_github_repo(
        name=project_title.lower().replace(" ", "-"),
        description=project_description,
        private=is_private,
    )
    if "error" in repo_result:
        return {"error": repo_result["error"], "project_description_saved": True, "repo_created": False}

    repo_full_name = repo_result.get("github_repo", repo_result.get("full_name", ""))

    # Set preferences
    _do_set_preference("github_repo_connected", True)
    _do_set_preference("confirm_arch_changes", confirm_arch_changes)

    # Lock session
    _do_set_session_repo(repo=repo_full_name)

    # Warm caches
    labels_result = _do_list_repo_labels()
    milestones_result = _do_list_milestones(state="open")

    return {
        "project_description_saved": True,
        "repo_created": True,
        "repo_url": repo_result.get("url", repo_result.get("html_url", "")),
        "repo_full_name": repo_full_name,
        "workspace_linked": True,
        "session_locked": True,
        "caches_warmed": {
            "labels": len(labels_result.get("labels", [])),
            "milestones": len(milestones_result.get("milestones", [])),
        },
        "preferences_saved": ["github_repo_connected", "confirm_arch_changes"],
        "ready_to_plan": True,
        "_display": f"✅ **Repo created** — {repo_full_name} | workspace linked | caches warmed",
    }
