"""Tests for server.py internals: get_github_client, get_workspace_root, prompt."""
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from terminal_hub.server import create_server, get_github_client, get_workspace_root


# ── get_workspace_root ────────────────────────────────────────────────────────

def test_get_workspace_root_returns_path():
    result = get_workspace_root()
    assert isinstance(result, Path)
    assert result == Path.cwd()


# ── get_github_client ─────────────────────────────────────────────────────────

def test_get_github_client_no_token_returns_none():
    from terminal_hub.auth import TokenSource
    with patch("terminal_hub.server.resolve_token", return_value=(None, TokenSource.NONE)):
        client, msg = get_github_client()
    assert client is None
    assert "check_auth" in msg


def test_get_github_client_success():
    from terminal_hub.auth import TokenSource
    with patch("terminal_hub.server.resolve_token", return_value=("tok", TokenSource.ENV)), \
         patch("terminal_hub.server.detect_repo", return_value="owner/repo"):
        client, msg = get_github_client()
    assert client is not None
    assert msg == ""
    assert client.repo == "owner/repo"


def test_get_github_client_no_repo_returns_error():
    from terminal_hub.auth import TokenSource
    with patch("terminal_hub.server.resolve_token", return_value=("tok", TokenSource.ENV)), \
         patch("terminal_hub.server.detect_repo", return_value=None):
        client, msg = get_github_client()
    assert client is None
    assert "setup_workspace" in msg


# ── terminal_hub_instructions prompt ─────────────────────────────────────────

def test_prompt_returns_instructions(tmp_path):
    from terminal_hub.prompts import TERMINAL_HUB_INSTRUCTIONS
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()

    prompt_fn = server._prompt_manager.get_prompt("terminal_hub_instructions")
    result = prompt_fn.fn()
    assert result == TERMINAL_HUB_INSTRUCTIONS


# ── create_issue: local write failure after GitHub success ────────────────────

def test_create_issue_local_write_failure_returns_warning(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    mock_gh = MagicMock()
    mock_gh.create_issue.return_value = {"number": 7, "html_url": "http://gh/7"}

    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path), \
         patch("terminal_hub.server.get_github_client", return_value=(mock_gh, "")), \
         patch("terminal_hub.server.write_issue_file", side_effect=OSError("disk full")):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool(
            "create_issue", {"title": "x", "body": "y"}
        ))

    assert result["issue_number"] == 7
    assert result["local_file"] is None
    assert result["warning"] == "local_write_failed"
    assert "disk full" in result["warning_message"]


# ── ensure_initialized guard ──────────────────────────────────────────────────

def test_tools_return_needs_init_when_hub_agents_missing(tmp_path):
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool("list_issues", {}))
    assert result["status"] == "needs_init"
