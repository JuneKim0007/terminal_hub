import asyncio
from datetime import date
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server
from terminal_hub.storage import write_issue_file


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def test_list_issues_empty(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "list_issues", {})
    assert result["issues"] == []


def test_list_issues_returns_all(workspace):
    write_issue_file(workspace, "fix-bug", "Fix bug", 1, "http://gh/1",
                     "body", [], [], date(2026, 3, 15))
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "list_issues", {})
    assert len(result["issues"]) == 1
    assert result["issues"][0]["slug"] == "fix-bug"


def test_list_issues_sorted_desc(workspace):
    for slug, day in [("issue-a", 10), ("issue-b", 15), ("issue-c", 5)]:
        write_issue_file(workspace, slug, slug, 1, f"http://gh/{slug}",
                         "body", [], [], date(2026, 3, day))
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "list_issues", {})
    slugs = [i["slug"] for i in result["issues"]]
    assert slugs == ["issue-b", "issue-a", "issue-c"]
