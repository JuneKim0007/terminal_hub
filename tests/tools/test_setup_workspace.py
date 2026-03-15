import asyncio
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".terminal_hub" / "issues").mkdir(parents=True)
    return tmp_path


def test_get_setup_status_not_configured(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_setup_status", {})
    assert result["configured"] is False
    assert "options" in result
    assert len(result["options"]) == 3


def test_get_setup_status_configured(workspace):
    from terminal_hub.config import WorkspaceMode, save_config
    save_config(workspace, WorkspaceMode.LOCAL, None)
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_setup_status", {})
    assert result["configured"] is True
    assert result["mode"] == "local"


def test_setup_local_mode(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "setup_workspace", {"mode": "local"})
    assert result["success"] is True
    assert result["mode"] == "local"
    assert (workspace / ".terminal_hub" / "config.yaml").exists()


def test_setup_github_mode(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "setup_workspace", {"mode": "github", "repo": "owner/my-repo"})
    assert result["success"] is True
    assert result["repo"] == "owner/my-repo"


def test_setup_connect_mode(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "setup_workspace", {"mode": "connect", "repo": "owner/existing"})
    assert result["success"] is True
    assert result["mode"] == "connect"


def test_setup_rejects_invalid_mode(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "setup_workspace", {"mode": "invalid"})
    assert result["error"] == "invalid_mode"


def test_setup_github_requires_repo(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "setup_workspace", {"mode": "github"})
    assert result["error"] == "missing_repo"
