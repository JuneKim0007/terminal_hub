"""Tests for gh_implementation extension tools."""
import asyncio
from pathlib import Path
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from terminal_hub.server import create_server
from extensions.github_planner.storage import write_issue_file, STATUS_PENDING, STATUS_OPEN


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


# ── get_implementation_session ────────────────────────────────────────────────

def test_get_implementation_session_returns_defaults(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_implementation_session", {})
    assert result["close_automatically_on_gh"] is True
    assert result["delete_local_issue_on_gh"] is True
    assert "_display" in result


# ── set_implementation_session_flag ──────────────────────────────────────────

def test_set_flag_updates_value(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "set_implementation_session_flag", {"key": "close_automatically_on_gh", "value": False})
        result = call(server, "get_implementation_session", {})
    assert result["close_automatically_on_gh"] is False


def test_set_flag_unknown_key_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "set_implementation_session_flag", {"key": "nonexistent", "value": True})
    assert result["error"] == "unknown_flag"


# ── update_issue_frontmatter ──────────────────────────────────────────────────

def test_update_issue_frontmatter_writes_fields(workspace):
    write_issue_file(
        root=workspace, slug="my-issue", title="Test", body="body",
        assignees=[], labels=[], created_at=date(2026, 3, 18), status=STATUS_PENDING,
    )
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_issue_frontmatter", {
            "slug": "my-issue",
            "fields": {"agent_workflow": ["Step A", "Step B"]},
        })
    assert result["slug"] == "my-issue"
    assert "agent_workflow" in result["updated_fields"]
    from extensions.github_planner.storage import read_issue_frontmatter
    fm = read_issue_frontmatter(workspace, "my-issue")
    assert fm["agent_workflow"] == ["Step A", "Step B"]


def test_update_issue_frontmatter_missing_file_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_issue_frontmatter", {"slug": "no-such", "fields": {"x": 1}})
    assert result["error"] == "issue_not_found"


# ── delete_local_issue ────────────────────────────────────────────────────────

def test_delete_local_issue_removes_file(workspace):
    write_issue_file(
        root=workspace, slug="to-delete", title="Delete me", body="body",
        assignees=[], labels=[], created_at=date(2026, 3, 18), status=STATUS_PENDING,
    )
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "delete_local_issue", {"slug": "to-delete"})
    assert result["deleted"] is True
    assert not (workspace / "hub_agents" / "issues" / "to-delete.md").exists()


def test_delete_local_issue_missing_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "delete_local_issue", {"slug": "no-such"})
    assert result["error"] == "not_found"


# ── fetch_github_issues ───────────────────────────────────────────────────────

def test_fetch_github_issues_writes_files(workspace):
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues.return_value = [
        {"number": 1, "title": "First issue", "body": "body1", "labels": [], "assignees": [], "html_url": "https://github.com/o/r/issues/1"},
        {"number": 2, "title": "Second issue", "body": "body2", "labels": [{"name": "bug"}], "assignees": [], "html_url": "https://github.com/o/r/issues/2"},
    ]
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_implementation.ensure_initialized", return_value=None):
        server = create_server()
        result = call(server, "fetch_github_issues", {"state": "open", "limit": 30})
    assert result["fetched"] == 2
    assert "1" in result["slugs"]
    assert (workspace / "hub_agents" / "issues" / "1.md").exists()
    assert (workspace / "hub_agents" / "issues" / "2.md").exists()


def test_fetch_github_issues_skips_existing(workspace):
    # Pre-create issue 1
    write_issue_file(
        root=workspace, slug="1", title="Existing", body="body",
        assignees=[], labels=[], created_at=date(2026, 3, 18), status=STATUS_OPEN,
    )
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues.return_value = [
        {"number": 1, "title": "Existing", "body": "body", "labels": [], "assignees": [], "html_url": ""},
    ]
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_implementation.ensure_initialized", return_value=None):
        server = create_server()
        result = call(server, "fetch_github_issues", {})
    assert result["fetched"] == 0  # skipped because file already exists


# ── close_github_issue ────────────────────────────────────────────────────────

def test_close_github_issue_calls_api(workspace):
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.close_issue.return_value = {"number": 42, "state": "closed"}
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_implementation.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_implementation.ensure_initialized", return_value=None):
        server = create_server()
        result = call(server, "close_github_issue", {"issue_number": 42})
    assert result["closed"] is True
    mock_gh.close_issue.assert_called_once_with(42, comment=None)
