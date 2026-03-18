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

from extensions.github_planner import get_github_client, get_workspace_root, ensure_initialized
from extensions.github_planner.storage import (
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
}

_ALLOWED_SESSION_FLAGS = {"close_automatically_on_gh", "delete_local_issue_on_gh"}


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
        "────────────────────────────────────────\n"
        "Say \"change X to false\" or use /th:gh-implementation/session-knowledge to update."
    )
    return {
        "close_automatically_on_gh": flags["close_automatically_on_gh"],
        "delete_local_issue_on_gh": flags["delete_local_issue_on_gh"],
        "_display": display,
    }


def _do_set_implementation_session_flag(key: str, value: bool, persist: bool = False) -> dict:
    if key not in _ALLOWED_SESSION_FLAGS:
        return {"error": "unknown_flag", "message": f"Unknown flag {key!r}. Allowed: {sorted(_ALLOWED_SESSION_FLAGS)}"}
    root = get_workspace_root()
    flags = _get_flags(root)
    flags[key] = value
    result = {"key": key, "value": value, "persisted": False, "_display": f"✓ {key} = {str(value).lower()}"}
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
        "_display": f"✓ Fetched {n} issue(s) from GitHub → hub_agents/issues/",
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
    return {"slug": slug, "updated_fields": list(fields.keys()), "_display": f"✓ Updated front matter for #{slug}"}


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
            "_display": f"✓ GitHub issue #{issue_number} closed",
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
    return {"deleted": True, "file": f"hub_agents/issues/{slug}.md", "_display": f"✓ Deleted hub_agents/issues/{slug}.md"}


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

        key: 'close_automatically_on_gh' | 'delete_local_issue_on_gh'
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
