"""Tests for get_session_state core tool."""
import asyncio
import json
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server


def call(server, tool_name, args=None):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args or {}))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    (tmp_path / "hub_agents" / "config.yaml").write_text("mode: github\n")
    (tmp_path / "hub_agents" / ".env").write_text("GITHUB_REPO=owner/repo\n")
    return tmp_path


def test_get_session_state_all_absent(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_session_state")
    assert "items" in result
    snap_item = next(i for i in result["items"] if i["key"] == "analyzer_snapshot")
    assert snap_item["status"] == "absent"


def test_get_session_state_snapshot_present(workspace):
    snap = {"analyzed_at": "2026-01-01T00:00:00+00:00", "repo": "r",
            "issues": {"label_frequency": {}, "assignee_frequency": {},
                       "title_prefixes": [], "avg_body_length": 0,
                       "body_sections": {}, "total_open": 0, "total_sampled": 0},
            "labels": [], "members": [], "templates": {
                "most_common_sections": [], "suggested_labels": [], "suggested_assignees": []}}
    snap_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "analyzer_snapshot.json").write_text(json.dumps(snap))
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_session_state")
    snap_item = next(i for i in result["items"] if i["key"] == "analyzer_snapshot")
    assert snap_item["status"] == "present"
    assert snap_item["size_bytes"] > 0


def test_get_session_state_display_present(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_session_state")
    assert "_display" in result
    assert "✗" in result["_display"]  # absent items shown with ✗


def test_get_session_state_not_initialized(tmp_path):
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "get_session_state")
    assert result.get("status") == "needs_init"


def test_get_session_state_items_structure(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_session_state")
    keys = {i["key"] for i in result["items"]}
    assert "analyzer_snapshot" in keys
    assert "project_summary" in keys
    assert "project_detail" in keys
    assert "issues" in keys


def test_get_session_state_with_issues(workspace):
    issue_content = "---\ntitle: Test\nstatus: pending\n---\nBody"
    (workspace / "hub_agents" / "issues" / "test-issue.md").write_text(issue_content)
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_session_state")
    issues_item = next(i for i in result["items"] if i["key"] == "issues")
    assert issues_item["status"] == "present"
    assert "1 total" in issues_item["summary"]


def test_get_session_state_config_returned(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_session_state")
    assert "config" in result
    assert result["config"].get("mode") == "github"


def test_get_session_state_display_has_header(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_session_state")
    assert "terminal-hub session state" in result["_display"]
    assert "owner/repo" in result["_display"]
