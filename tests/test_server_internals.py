"""Tests for server.py internals: get_github_client, get_workspace_root, prompt."""
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from terminal_hub.server import create_server
from plugins.github_planner import get_github_client, get_workspace_root


# ── get_workspace_root ────────────────────────────────────────────────────────

def test_get_workspace_root_returns_path():
    result = get_workspace_root()
    assert isinstance(result, Path)
    assert result == Path.cwd()


# ── get_github_client ─────────────────────────────────────────────────────────

def test_get_github_client_no_token_returns_none():
    from plugins.github_planner.auth import TokenSource
    with patch("plugins.github_planner.resolve_token", return_value=(None, TokenSource.NONE)):
        client, msg = get_github_client()
    assert client is None
    assert "check_auth" in msg


def test_get_github_client_success():
    from plugins.github_planner.auth import TokenSource
    with patch("plugins.github_planner.resolve_token", return_value=("tok", TokenSource.ENV)), \
         patch("plugins.github_planner.detect_repo", return_value="owner/repo"):
        client, msg = get_github_client()
    assert client is not None
    assert msg == ""
    assert client.repo == "owner/repo"


def test_get_github_client_no_repo_returns_error():
    from plugins.github_planner.auth import TokenSource
    with patch("plugins.github_planner.resolve_token", return_value=("tok", TokenSource.ENV)), \
         patch("plugins.github_planner.detect_repo", return_value=None):
        client, msg = get_github_client()
    assert client is None
    assert "setup_workspace" in msg


# ── terminal_hub_instructions prompt ─────────────────────────────────────────

def test_server_instructions_on_demand_message(tmp_path):
    with patch("plugins.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
    assert "terminal-hub connected" in server.instructions


# ── draft_issue: local write failure ─────────────────────────────────────────

def test_draft_issue_local_write_failure_returns_error(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)

    with patch("plugins.github_planner.get_workspace_root", return_value=tmp_path), \
         patch("plugins.github_planner.write_issue_file", side_effect=OSError("disk full")):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool(
            "draft_issue", {"title": "x", "body": "y"}
        ))

    assert result["error"] == "draft_failed"
    assert result["_hook"] is None


# ── ensure_initialized guard ──────────────────────────────────────────────────

def test_tools_return_needs_init_when_hub_agents_missing(tmp_path):
    with patch("plugins.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool("list_issues", {}))
    assert result["status"] == "needs_init"
