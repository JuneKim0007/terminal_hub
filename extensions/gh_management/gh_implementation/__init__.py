"""gh_implementation extension — end-to-end issue implementation flow.

Tools: get_implementation_session, set_implementation_session_flag,
       fetch_github_issues, update_issue_frontmatter,
       close_github_issue, delete_local_issue
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from extensions.gh_management.github_planner import get_github_client, get_workspace_root, ensure_initialized
from extensions.gh_management.github_planner.storage import (
    _issues_dir, _atomic_write, validate_slug,
    read_issue_frontmatter, list_issue_files, IssueStatus, write_issue_file,
)
from terminal_hub.env_store import read_env

# ── In-memory session state ───────────────────────────────────────────────────
# Keyed by workspace root str so multi-workspace scenarios don't collide.
_SESSION_FLAGS: dict[str, dict[str, Any]] = {}

_DEFAULT_FLAGS: dict[str, Any] = {
    "close_automatically_on_gh": True,
    "delete_local_issue_on_gh": True,
    "confirmed_auto_close_this_session": False,  # internal — True after "don't ask again"
    "active_issue_slug": None,
}

_ALLOWED_SESSION_FLAGS = {"close_automatically_on_gh", "delete_local_issue_on_gh", "auto_switch_modes"}


def _get_flags(root: Path) -> dict[str, Any]:
    key = str(root)
    if key not in _SESSION_FLAGS:
        _SESSION_FLAGS[key] = dict(_DEFAULT_FLAGS)
    return _SESSION_FLAGS[key]


def _do_get_implementation_session() -> dict:
    root = get_workspace_root()
    flags = _get_flags(root)
    display = (
        "Implementation session flags\n"
        "────────────────────────────────────────\n"
        f"  close_automatically_on_gh   {'true' if flags['close_automatically_on_gh'] else 'false'}"
        "    Push, close branch, and close GitHub issue automatically after accepting changes\n"
        f"  delete_local_issue_on_gh    {'true' if flags['delete_local_issue_on_gh'] else 'false'}"
        "    Delete hub_agents/issues/<slug>.md after GitHub issue is closed\n"
        f"  active_issue_slug           {flags.get('active_issue_slug') or 'none'}"
        "    Currently hooked issue — set automatically by load_active_issue\n"
        "────────────────────────────────────────\n"
        "Say \"change X to false\" or use /th:gh-implementation/session-knowledge to update."
    )
    return {
        "close_automatically_on_gh": flags["close_automatically_on_gh"],
        "delete_local_issue_on_gh": flags["delete_local_issue_on_gh"],
        "_display": display,
    }


def _do_load_active_issue(slug: str) -> dict:
    try:
        validate_slug(slug)
    except ValueError as exc:
        return {"error": "invalid_slug", "message": str(exc)}
    root = get_workspace_root()
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return {"error": "issue_not_found", "message": f"No issue file for slug {slug!r}"}
    content = path.read_text(encoding="utf-8")
    fm = read_issue_frontmatter(root, slug) or {}
    _get_flags(root)["active_issue_slug"] = slug
    return {
        "slug": slug,
        "content": content,
        "title": fm.get("title", ""),
        "labels": fm.get("labels", []),
        "agent_workflow": fm.get("agent_workflow"),
        "_display": f"✅ **Hooked:** issue #{slug} — {fm.get('title', '')} loaded into context",
    }


def _do_unload_active_issue(slug: str | None = None, delete_file: bool | None = None) -> dict:
    root = get_workspace_root()
    flags = _get_flags(root)
    target_slug = slug or flags.get("active_issue_slug")
    if not target_slug:
        return {"unloaded": False, "message": "No active issue in session"}
    flags.pop("active_issue_slug", None)
    should_delete = delete_file if delete_file is not None else flags.get("delete_local_issue_on_gh", True)
    deleted = False
    if should_delete:
        path = _issues_dir(root) / f"{target_slug}.md"
        if path.exists():
            path.unlink()
            deleted = True
    return {
        "unloaded": True,
        "slug": target_slug,
        "file_deleted": deleted,
        "_display": f"✅ **Unhooked:** issue #{target_slug} — context cleared{', file deleted' if deleted else ''}",
    }


def _do_set_implementation_session_flag(key: str, value: bool, persist: bool = False) -> dict:
    if key not in _ALLOWED_SESSION_FLAGS:
        return {"error": "unknown_flag", "message": f"Unknown flag {key!r}. Allowed: {sorted(_ALLOWED_SESSION_FLAGS)}"}
    root = get_workspace_root()
    flags = _get_flags(root)
    flags[key] = value
    result = {"key": key, "value": value, "persisted": False, "_display": f"✅ **Flag set:** `{key}` = {str(value).lower()}"}
    if persist:
        try:
            from terminal_hub.config import write_preference
            write_preference(root, f"gh_implementation.{key}", value)
            result["persisted"] = True
        except Exception as exc:
            result["persist_warning"] = str(exc)
    return result


def _do_fetch_github_issues(state: str = "open", limit: int = 30) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    gh, err = get_github_client()
    if gh is None:
        return err
    issues_dir = _issues_dir(root)
    issues_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    try:
        with gh:
            raw_issues = gh.list_issues(state=state, limit=limit)
    except Exception as exc:
        return {"error": "fetch_failed", "message": str(exc)}

    for issue in raw_issues:
        number = issue.get("number")
        slug = str(number)
        path = issues_dir / f"{slug}.md"
        if path.exists():
            continue  # already synced
        labels = [l["name"] for l in issue.get("labels", [])]
        assignees = [a["login"] for a in issue.get("assignees", [])]
        write_issue_file(
            root=root,
            slug=slug,
            title=issue.get("title", ""),
            body=issue.get("body") or "",
            assignees=assignees,
            labels=labels,
            created_at=date.today(),
            status=IssueStatus.OPEN,
            issue_number=number,
            github_url=issue.get("html_url"),
        )
        created.append(slug)

    n = len(created)
    return {
        "fetched": n,
        "slugs": created,
        "_display": f"✅ **Fetched** {n} issue(s) from GitHub",
    }


def _do_update_issue_frontmatter(slug: str, fields: dict[str, Any]) -> dict:
    """Atomically update specific front matter fields on an existing issue file."""
    try:
        validate_slug(slug)
    except ValueError as exc:
        return {"error": "invalid_slug", "message": str(exc)}
    root = get_workspace_root()
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return {"error": "issue_not_found", "message": f"No issue file for slug {slug!r}"}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {"error": "no_frontmatter", "message": "Issue file has no YAML front matter"}
    parts = text.split("---", 2)
    fm: dict[str, Any] = yaml.safe_load(parts[1]) or {}
    body = parts[2] if len(parts) > 2 else ""
    fm.update(fields)
    updated = f"---\n{yaml.dump(fm, default_flow_style=False)}---{body}"
    _atomic_write(path, updated)
    return {"slug": slug, "updated_fields": list(fields.keys()), "_display": f"✅ **Updated** front matter for #{slug}"}


def _do_close_github_issue(issue_number: int, comment: str | None = None) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    gh, err = get_github_client()
    if gh is None:
        return err
    try:
        with gh:
            gh.close_issue(issue_number, comment=comment)
        return {
            "issue_number": issue_number,
            "closed": True,
            "_display": f"**✅ Closed** issue #{issue_number} on GitHub",
        }
    except Exception as exc:
        return {"error": "close_failed", "message": str(exc)}


def _do_delete_local_issue(slug: str) -> dict:
    try:
        validate_slug(slug)
    except ValueError as exc:
        return {"error": "invalid_slug", "message": str(exc)}
    root = get_workspace_root()
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return {"error": "not_found", "message": f"No local issue file for {slug!r}"}
    path.unlink()
    return {"deleted": True, "file": f"hub_agents/issues/{slug}.md", "_display": f"🗑 **Deleted** local issue #{slug}"}


def register(mcp: FastMCP) -> None:
    """Register gh_implementation tools on the shared MCP server."""

    @mcp.tool()
    def get_implementation_session() -> dict:
        """Return current session-scoped implementation flags.

        Flags (reset each session unless persisted):
          close_automatically_on_gh: push + close issue on GitHub after user accepts changes
          delete_local_issue_on_gh:  delete local hub_agents/issues/<slug>.md after GH close
        """
        return _do_get_implementation_session()

    @mcp.tool()
    def set_implementation_session_flag(key: str, value: bool, persist: bool = False) -> dict:
        """Update a session-scoped implementation flag.

        key: 'close_automatically_on_gh' | 'delete_local_issue_on_gh' | 'auto_switch_modes'
        value: true | false
        persist: if true, write to hub_agents/config.yaml preferences so it survives sessions
        """
        return _do_set_implementation_session_flag(key, value, persist)

    @mcp.tool()
    def fetch_github_issues(state: str = "open", limit: int = 30) -> dict:
        """Fetch issues from GitHub and write them to hub_agents/issues/.

        Skips issues that already have a local file (by issue number slug).
        state: 'open' | 'closed' | 'all'
        limit: max issues to fetch (default 30)
        Returns {fetched, slugs, _display}.
        """
        return _do_fetch_github_issues(state, limit)

    @mcp.tool()
    def update_issue_frontmatter(slug: str, fields: dict) -> dict:
        """Atomically update specific front matter fields on an existing issue file.

        Only updates the provided keys — leaves body and all other fields unchanged.
        Use this to write agent_workflow, status, or any other front matter field.

        slug: issue slug (e.g. '42' or 'fix-auth-bug')
        fields: dict of front matter keys to update
        """
        return _do_update_issue_frontmatter(slug, fields)

    @mcp.tool()
    def close_github_issue(issue_number: int, comment: str | None = None) -> dict:
        """Close a GitHub issue via the API.

        issue_number: the GitHub issue number (not local slug)
        comment: optional closing comment to post before closing
        """
        return _do_close_github_issue(issue_number, comment)

    @mcp.tool()
    def delete_local_issue(slug: str) -> dict:
        """Delete a local issue file from hub_agents/issues/<slug>.md.

        slug: issue slug (e.g. '42' or 'fix-auth-bug')
        Returns {deleted, file}.
        """
        return _do_delete_local_issue(slug)

    @mcp.tool()
    def load_active_issue(slug: str) -> dict:
        """Hook an issue into the active implementation session.

        Reads hub_agents/issues/<slug>.md, injects full content into the response,
        and sets active_issue_slug in session state.

        Call this as the FIRST action in Step 4 of the implement flow — mandatory.
        The returned content and agent_workflow are the authoritative issue context;
        do not re-read the file separately.

        slug: issue slug (e.g. '42')
        Returns {slug, content, title, labels, agent_workflow, _display}.
        """
        return _do_load_active_issue(slug)

    @mcp.tool()
    def unload_active_issue(slug: str | None = None, delete_file: bool | None = None) -> dict:
        """Unhook the active issue and clean up session state.

        Clears active_issue_slug from session. Deletes the local issue file
        according to the delete_local_issue_on_gh flag unless overridden.

        Call this as the ONLY action in Step 10 of the implement flow — mandatory.

        slug: override the active slug (default: use session-tracked slug)
        delete_file: override the delete_local_issue_on_gh flag (True/False/None=use flag)
        Returns {unloaded, slug, file_deleted, _display}.
        """
        return _do_unload_active_issue(slug, delete_file)
