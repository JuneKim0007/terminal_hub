"""Tests for terminal-hub install/verify CLI commands."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from terminal_hub.install import build_mcp_config, read_claude_json, write_claude_json, run_install, run_verify


@pytest.fixture
def claude_json(tmp_path):
    path = tmp_path / ".claude.json"
    path.write_text(json.dumps({"mcpServers": {}}))
    return path


# ── build_mcp_config ──────────────────────────────────────────────────────────

def test_build_config_has_no_project_env_vars():
    cfg = build_mcp_config()
    assert "env" not in cfg


def test_build_config_args():
    assert build_mcp_config()["args"] == ["-m", "terminal_hub"]


def test_build_config_has_command():
    assert build_mcp_config()["command"]


# ── read_claude_json ──────────────────────────────────────────────────────────

def test_read_missing_returns_empty(tmp_path):
    assert read_claude_json(tmp_path / "nope.json") == {}


def test_read_invalid_json_returns_empty(tmp_path):
    bad = tmp_path / ".claude.json"
    bad.write_text("not {{ json")
    assert read_claude_json(bad) == {}


def test_read_valid_json(claude_json):
    assert isinstance(read_claude_json(claude_json), dict)


# ── write_claude_json ─────────────────────────────────────────────────────────

def test_write_adds_global_entry(claude_json):
    write_claude_json(claude_json, build_mcp_config())
    data = json.loads(claude_json.read_text())
    assert "terminal-hub" in data["mcpServers"]


def test_write_preserves_other_servers(claude_json):
    claude_json.write_text(json.dumps({"mcpServers": {"other": {"command": "foo"}}}))
    write_claude_json(claude_json, build_mcp_config())
    data = json.loads(claude_json.read_text())
    assert "other" in data["mcpServers"]
    assert "terminal-hub" in data["mcpServers"]


def test_write_no_projects_key(claude_json):
    write_claude_json(claude_json, build_mcp_config())
    assert "projects" not in json.loads(claude_json.read_text())


# ── run_install ───────────────────────────────────────────────────────────────

def test_run_install_writes_entry(claude_json):
    with patch("builtins.input", return_value="y"):
        run_install(claude_json_path=claude_json)
    data = json.loads(claude_json.read_text())
    assert "terminal-hub" in data["mcpServers"]


def test_run_install_aborts_on_no(claude_json):
    with patch("builtins.input", return_value="n"), pytest.raises(SystemExit):
        run_install(claude_json_path=claude_json)
    assert "terminal-hub" not in json.loads(claude_json.read_text()).get("mcpServers", {})


# ── run_verify ────────────────────────────────────────────────────────────────

def test_run_verify_passes_when_installed(claude_json, capsys):
    with patch("builtins.input", return_value="y"):
        run_install(claude_json_path=claude_json)
    run_verify(claude_json_path=claude_json)
    assert "✓" in capsys.readouterr().out


def test_run_verify_fails_when_not_installed(claude_json):
    with pytest.raises(SystemExit):
        run_verify(claude_json_path=claude_json)
