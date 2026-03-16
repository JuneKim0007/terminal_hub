"""Tests for get_setup_status with existing hub_agents/ data."""
import asyncio
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


def test_not_initialised_when_hub_agents_missing(tmp_path):
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "get_setup_status", {})
    assert result["initialised"] is False


def test_initialised_when_hub_agents_exists(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    from terminal_hub.config import WorkspaceMode, save_config
    save_config(tmp_path, WorkspaceMode.LOCAL, None)
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "get_setup_status", {})
    assert result["initialised"] is True


def test_github_repo_returned_when_configured(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    from terminal_hub.config import WorkspaceMode, save_config
    from terminal_hub.env_store import write_env
    save_config(tmp_path, WorkspaceMode.GITHUB, "owner/repo")
    write_env(tmp_path, {"GITHUB_REPO": "owner/repo"})
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "get_setup_status", {})
    assert result["github_repo"] == "owner/repo"
