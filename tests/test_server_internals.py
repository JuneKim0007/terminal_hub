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

def test_server_instructions_loaded_from_entry_point(tmp_path):
    from terminal_hub.server import _load_agent
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
    assert server.instructions == _load_agent("entry_point.md")


# ── draft_issue: local write failure ─────────────────────────────────────────

def test_draft_issue_local_write_failure_returns_error(tmp_path):
    import json
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)

    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path), \
         patch("terminal_hub.server.write_issue_file", side_effect=OSError("disk full")):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool(
            "draft_issue", {"issue_json": json.dumps({"title": "x", "body": "y"})}
        ))

    assert result["error"] == "draft_failed"
    assert result["_hook"] is None


# ── ensure_initialized guard ──────────────────────────────────────────────────

def test_tools_return_needs_init_when_hub_agents_missing(tmp_path):
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool("list_issues", {}))
    assert result["status"] == "needs_init"
