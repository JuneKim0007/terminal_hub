"""Tests for get_setup_status detecting existing .terminal_hub/ data."""
import asyncio
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


def test_has_existing_data_when_issues_present(tmp_path):
    """Returning workspace: .terminal_hub/issues/ exists but no config.yaml."""
    (tmp_path / ".terminal_hub" / "issues").mkdir(parents=True)
    (tmp_path / ".terminal_hub" / "issues" / "old-issue.md").write_text("---\ntitle: old\n---\n")

    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "get_setup_status", {})

    assert result["configured"] is False
    assert result["has_existing_data"] is True


def test_no_existing_data_on_fresh_workspace(tmp_path):
    (tmp_path / ".terminal_hub" / "issues").mkdir(parents=True)

    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "get_setup_status", {})

    assert result["configured"] is False
    assert result["has_existing_data"] is False


def test_configured_does_not_include_has_existing_data(tmp_path):
    from terminal_hub.config import WorkspaceMode, save_config
    (tmp_path / ".terminal_hub" / "issues").mkdir(parents=True)
    save_config(tmp_path, WorkspaceMode.LOCAL, None)

    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "get_setup_status", {})

    assert result["configured"] is True
    assert "has_existing_data" not in result
