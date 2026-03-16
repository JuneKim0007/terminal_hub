"""Tests for terminal-hub install command (global install)."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from terminal_hub.install import build_mcp_config, write_claude_json, read_claude_json


@pytest.fixture
def claude_json(tmp_path):
    path = tmp_path / ".claude.json"
    path.write_text(json.dumps({"mcpServers": {}}))
    return path


# ── build_mcp_config ──────────────────────────────────────────────────────────

def test_build_config_has_no_env_vars():
    cfg = build_mcp_config()
    assert "env" not in cfg
    assert cfg["args"] == ["-m", "terminal_hub"]


def test_build_config_has_command():
    cfg = build_mcp_config()
    assert "command" in cfg
    assert cfg["command"]  # non-empty


# ── read_claude_json ──────────────────────────────────────────────────────────

def test_read_claude_json_returns_dict(claude_json):
    result = read_claude_json(claude_json)
    assert isinstance(result, dict)


def test_read_claude_json_missing_file_returns_empty(tmp_path):
    result = read_claude_json(tmp_path / "nonexistent.json")
    assert result == {}


def test_read_claude_json_invalid_json_returns_empty(tmp_path):
    bad = tmp_path / ".claude.json"
    bad.write_text("not json {{")
    result = read_claude_json(bad)
    assert result == {}


# ── write_claude_json ─────────────────────────────────────────────────────────

def test_write_adds_global_mcp_entry(claude_json):
    cfg = build_mcp_config()
    write_claude_json(claude_json, cfg)

    data = json.loads(claude_json.read_text())
    assert "terminal-hub" in data["mcpServers"]


def test_write_preserves_existing_mcp_servers(claude_json):
    existing = {"mcpServers": {"other-tool": {"command": "foo"}}}
    claude_json.write_text(json.dumps(existing))

    write_claude_json(claude_json, build_mcp_config())

    data = json.loads(claude_json.read_text())
    assert "other-tool" in data["mcpServers"]
    assert "terminal-hub" in data["mcpServers"]


def test_write_overwrites_existing_terminal_hub_entry(claude_json):
    old = {"mcpServers": {"terminal-hub": {"command": "old"}}}
    claude_json.write_text(json.dumps(old))

    write_claude_json(claude_json, build_mcp_config())

    data = json.loads(claude_json.read_text())
    assert data["mcpServers"]["terminal-hub"]["command"] != "old"


def test_write_does_not_create_projects_key(claude_json):
    write_claude_json(claude_json, build_mcp_config())
    data = json.loads(claude_json.read_text())
    assert "projects" not in data
