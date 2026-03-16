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


def test_get_setup_status_not_initialised(tmp_path):
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "get_setup_status", {})
    assert result["initialised"] is False
    assert "message" in result


def test_get_setup_status_initialised(workspace):
    from terminal_hub.config import WorkspaceMode, save_config
    save_config(workspace, WorkspaceMode.LOCAL, None)
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_setup_status", {})
    assert result["initialised"] is True
    assert result["mode"] == "local"


def test_setup_local_mode(tmp_path):
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "setup_workspace", {})
    assert result["success"] is True
    assert (tmp_path / "hub_agents" / "config.yaml").exists()


def test_setup_with_github_repo(tmp_path):
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "setup_workspace", {"github_repo": "owner/my-repo"})
    assert result["success"] is True
    assert result["github_repo"] == "owner/my-repo"
    from terminal_hub.env_store import read_env
    assert read_env(tmp_path)["GITHUB_REPO"] == "owner/my-repo"


def test_setup_creates_hub_agents_dir(tmp_path):
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        call(server, "setup_workspace", {})
    assert (tmp_path / "hub_agents").exists()


def test_setup_gitignores_hub_agents(tmp_path):
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        call(server, "setup_workspace", {})
    assert "hub_agents/" in (tmp_path / ".gitignore").read_text()
