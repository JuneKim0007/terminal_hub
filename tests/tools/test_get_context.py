import asyncio
from datetime import date
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server
from terminal_hub.storage import write_doc_file, write_issue_file


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def test_get_project_context_single(workspace):
    write_doc_file(workspace, "project_description", "# Project\n")
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_project_context", {"file": "project_description"})
    assert result["content"] == "# Project\n"


def test_get_project_context_not_found(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_project_context", {"file": "project_description"})
    assert result["content"] is None


def test_get_project_context_all(workspace):
    write_doc_file(workspace, "project_description", "# Project\n")
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_project_context", {"file": "all"})
    assert result["project_description"] == "# Project\n"
    assert result["architecture"] is None


def test_get_issue_context_found(workspace):
    write_issue_file(root=workspace, slug="fix-bug", title="Fix bug",
                     body="body", assignees=[], labels=[], created_at=date(2026, 3, 15))
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_issue_context", {"slug": "fix-bug"})
    assert result["slug"] == "fix-bug"
    assert "Fix bug" in result["content"]


def test_get_issue_context_not_found(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_issue_context", {"slug": "no-such-issue"})
    assert result["error"] == "not_found"
    assert "no-such-issue" in result["message"]
