import asyncio
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def test_update_project_description_writes_file(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_description", {"content": "# My Project\n"})
    assert result["updated"] is True
    assert (workspace / "hub_agents" / "project_description.md").read_text() == "# My Project\n"


def test_update_project_description_returns_relative_path(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_description", {"content": "text"})
    assert "hub_agents/project_description.md" in result["file"]


def test_update_architecture_writes_file(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_architecture", {"content": "# Architecture\n"})
    assert result["updated"] is True
    assert (workspace / "hub_agents" / "architecture_design.md").read_text() == "# Architecture\n"


def test_update_docs_overwrite_preserves_latest(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "update_project_description", {"content": "v1"})
        call(server, "update_project_description", {"content": "v2"})
    assert (workspace / "hub_agents" / "project_description.md").read_text() == "v2"
