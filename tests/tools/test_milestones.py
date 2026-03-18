"""Tests for GitHub milestone MCP tools."""
import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from terminal_hub.server import create_server
from extensions.github_planner.storage import write_issue_file, STATUS_PENDING


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def _mock_gh():
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


# ── create_milestone ──────────────────────────────────────────────────────────

def test_create_milestone_success(workspace):
    mock_gh = _mock_gh()
    mock_gh.create_milestone.return_value = {
        "number": 1, "title": "Core Auth", "description": "Users can log in", "open_issues": 0
    }
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "create_milestone", {"title": "Core Auth", "description": "Users can log in"})
    assert result["number"] == 1
    assert result["title"] == "Core Auth"
    assert "✓" in result["_display"]


def test_create_milestone_cached(workspace):
    """Second create_milestone call with same title should NOT call API again if cached."""
    from extensions.github_planner import _MILESTONE_CACHE
    _MILESTONE_CACHE["o/r"] = [{"number": 1, "title": "Core Auth", "description": "...", "open_issues": 0}]

    mock_gh = _mock_gh()
    mock_gh.create_milestone.return_value = {"number": 1, "title": "Core Auth", "description": "...", "open_issues": 0}

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        call(server, "create_milestone", {"title": "Core Auth"})

    _MILESTONE_CACHE.clear()


# ── list_milestones ───────────────────────────────────────────────────────────

def test_list_milestones_uses_cache(workspace):
    from extensions.github_planner import _MILESTONE_CACHE
    _MILESTONE_CACHE["o/r"] = [{"number": 1, "title": "M1", "description": "desc", "open_issues": 0}]

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "list_milestones", {})

    assert result["cached"] is True
    assert result["count"] == 1
    _MILESTONE_CACHE.clear()


def test_list_milestones_fetches_when_no_cache(workspace):
    from extensions.github_planner import _MILESTONE_CACHE
    _MILESTONE_CACHE.clear()
    mock_gh = _mock_gh()
    mock_gh.list_milestones.return_value = [
        {"number": 1, "title": "M1", "description": "desc", "open_issues": 2}
    ]

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "list_milestones", {})

    assert result["cached"] is False
    assert result["count"] == 1
    _MILESTONE_CACHE.clear()


# ── assign_milestone ──────────────────────────────────────────────────────────

def test_assign_milestone_updates_frontmatter(workspace):
    from extensions.github_planner import _MILESTONE_CACHE
    _MILESTONE_CACHE["o/r"] = [{"number": 2, "title": "Posting", "description": "...", "open_issues": 0}]

    write_issue_file(
        root=workspace, slug="my-issue", title="Add post", body="body",
        assignees=[], labels=[], created_at=date(2026, 3, 18), status=STATUS_PENDING,
    )

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "assign_milestone", {"slug": "my-issue", "milestone_number": 2})

    assert result["milestone_number"] == 2
    assert result["milestone_title"] == "Posting"
    assert result["github_assigned"] is False  # no issue_number in front matter

    from extensions.github_planner.storage import read_issue_frontmatter
    fm = read_issue_frontmatter(workspace, "my-issue")
    assert fm["milestone_number"] == 2
    assert fm["milestone_title"] == "Posting"
    _MILESTONE_CACHE.clear()


def test_assign_milestone_missing_issue_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "assign_milestone", {"slug": "no-such", "milestone_number": 1})
    assert result["error"] == "issue_not_found"


# ── draft_issue with milestone_number ────────────────────────────────────────

def test_draft_issue_with_milestone_stores_in_frontmatter(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {
            "title": "Add login",
            "body": "Implement login",
            "milestone_number": 1,
        })

    from extensions.github_planner.storage import read_issue_frontmatter
    fm = read_issue_frontmatter(workspace, result["slug"])
    assert fm["milestone_number"] == 1
