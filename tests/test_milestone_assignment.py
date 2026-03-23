"""Tests for milestone pre-flight check in submit_issue (#49)."""
import asyncio
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from terminal_hub.server import create_server
from extensions.gh_management.github_planner.storage import STATUS_PENDING, write_issue_file


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def _mock_gh(number=42, url="https://github.com/o/r/issues/42"):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.create_issue.return_value = {"number": number, "html_url": url}
    mock.ensure_labels.return_value = None
    return mock


# ── test_submit_with_missing_milestone_returns_error ──────────────────────────

def test_submit_with_missing_milestone_returns_error(workspace):
    """submit_issue returns milestone_not_found when milestone_number not in cache."""
    from extensions.gh_management.github_planner import _MILESTONE_CACHE

    # Cache is warm but milestone #5 is NOT in it
    _MILESTONE_CACHE["o/r"] = [{"number": 1, "title": "M1", "description": "", "open_issues": 0}]

    write_issue_file(
        root=workspace, slug="5", title="My issue", body="body",
        assignees=[], labels=[], created_at=date(2026, 3, 19), status=STATUS_PENDING,
        milestone_number=5,
    )

    mock_gh = _mock_gh()
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "5"})

    assert result["error"] == "milestone_not_found"
    assert result["milestone_number"] == 5
    assert "_display" in result
    assert "Milestone #5" in result["_display"] or "milestone" in result["_display"].lower()

    # Verify GitHub API was NOT called (issue was not created)
    mock_gh.create_issue.assert_not_called()

    _MILESTONE_CACHE.clear()


# ── test_submit_with_valid_milestone_proceeds ─────────────────────────────────

def test_submit_with_valid_milestone_proceeds(workspace):
    """submit_issue proceeds normally when milestone is present in cache."""
    from extensions.gh_management.github_planner import _MILESTONE_CACHE

    # Milestone #2 IS in the cache
    _MILESTONE_CACHE["o/r"] = [{"number": 2, "title": "M2", "description": "", "open_issues": 0}]

    write_issue_file(
        root=workspace, slug="10", title="Valid milestone issue", body="body",
        assignees=[], labels=[], created_at=date(2026, 3, 19), status=STATUS_PENDING,
        milestone_number=2,
    )

    mock_gh = _mock_gh(number=10)
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "10"})

    # Should succeed — no milestone_not_found error
    assert "error" not in result or result.get("error") is None
    assert result.get("issue_number") == 10
    mock_gh.create_issue.assert_called_once()

    _MILESTONE_CACHE.clear()
