"""Tests for run_analyzer MCP tool and related __init__.py lines 294-337, 451."""
import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from terminal_hub.server import create_server


def call(server, tool_name, args=None):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args or {}))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    (tmp_path / "hub_agents" / ".env").write_text("GITHUB_REPO=owner/repo\n")
    return tmp_path


def _mock_gh():
    mock = MagicMock()
    mock.list_issues.return_value = [
        {
            "title": "Fix bug",
            "body": "## Description\nfix it",
            "state": "open",
            "labels": [{"name": "bug"}],
            "assignees": [{"login": "alice"}],
        }
    ]
    mock.list_labels.return_value = [{"name": "bug", "color": "d73a4a", "description": ""}]
    mock.list_collaborators.return_value = [{"login": "alice"}]
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


# ── run_analyzer: success path (lines 294-341) ────────────────────────────────

def test_run_analyzer_success_writes_snapshot(workspace):
    """Lines 294-341: successful run writes analyzer_snapshot.json."""
    with patch("extensions.github_planner._get_github_client", return_value=(_mock_gh(), "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "run_analyzer")

    assert "_display" in result
    snapshot_path = workspace / "hub_agents" / "analyzer_snapshot.json"
    assert snapshot_path.exists()
    snapshot = json.loads(snapshot_path.read_text())
    assert snapshot["repo"] == "owner/repo"


def test_run_analyzer_success_display_contains_repo(workspace):
    """Lines 326-335: display string mentions repo name."""
    with patch("extensions.github_planner._get_github_client", return_value=(_mock_gh(), "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "run_analyzer")

    assert "owner/repo" in result["_display"]


def test_run_analyzer_success_snapshot_file_in_result(workspace):
    """Lines 337-341: result contains snapshot_file path."""
    with patch("extensions.github_planner._get_github_client", return_value=(_mock_gh(), "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "run_analyzer")

    assert "snapshot_file" in result
    assert "analyzer_snapshot.json" in result["snapshot_file"]


# ── run_analyzer: no auth (line 302-303) ─────────────────────────────────────

def test_run_analyzer_no_auth_returns_error(workspace):
    """Lines 302-303: GitHub client unavailable → github_unavailable error."""
    with patch("extensions.github_planner._get_github_client", return_value=(None, "No auth.")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "run_analyzer")

    assert result["error"] == "github_unavailable"
    assert result["message"] == "No auth."


# ── run_analyzer: not initialized (line 298-299) ──────────────────────────────

def test_run_analyzer_not_initialized_returns_needs_init(tmp_path):
    """Lines 297-299: hub_agents/ absent → needs_init status."""
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "run_analyzer")

    assert result["status"] == "needs_init"


# ── run_analyzer: GitHub API error (lines 313-314) ───────────────────────────

def test_run_analyzer_github_api_error_returns_github_error(workspace):
    """Lines 313-314: exception from list_issues → github_error."""
    mock_gh = _mock_gh()
    mock_gh.list_issues.side_effect = Exception("API down")

    with patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "run_analyzer")

    assert result["error"] == "github_error"
    assert "API down" in result["message"]


def test_run_analyzer_github_list_labels_error_returns_github_error(workspace):
    """Lines 313-314: exception from list_labels → github_error."""
    mock_gh = _mock_gh()
    mock_gh.list_labels.side_effect = RuntimeError("labels endpoint down")

    with patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "run_analyzer")

    assert result["error"] == "github_error"


# ── run_analyzer tool is registered (line 451) ───────────────────────────────

def test_run_analyzer_tool_is_registered(workspace):
    """Line 451: run_analyzer is available on the server tool list."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
    tool_names = [t.name for t in server._tool_manager.list_tools()]
    assert "run_analyzer" in tool_names
