"""Tests for install.py interactive flow."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from terminal_hub.install import run_install, run_verify, build_mcp_config, format_diff


@pytest.fixture
def claude_json(tmp_path):
    path = tmp_path / ".claude.json"
    path.write_text(json.dumps({"mcpServers": {}}))
    return path


# ── format_diff ───────────────────────────────────────────────────────────────

def test_format_diff_contains_terminal_hub():
    cfg = build_mcp_config()
    diff = format_diff(cfg)
    assert "terminal-hub" in diff
    assert "global" in diff


# ── run_install ───────────────────────────────────────────────────────────────

def test_run_install_writes_global_mcp_entry(claude_json):
    with patch("builtins.input", return_value="y"):
        run_install(claude_json_path=claude_json)

    data = json.loads(claude_json.read_text())
    assert "terminal-hub" in data["mcpServers"]


def test_run_install_no_env_vars_in_config(claude_json):
    with patch("builtins.input", return_value="y"):
        run_install(claude_json_path=claude_json)

    data = json.loads(claude_json.read_text())
    entry = data["mcpServers"]["terminal-hub"]
    assert "env" not in entry


def test_run_install_aborts_on_no(claude_json):
    with patch("builtins.input", return_value="n"), pytest.raises(SystemExit):
        run_install(claude_json_path=claude_json)

    data = json.loads(claude_json.read_text())
    assert "terminal-hub" not in data.get("mcpServers", {})


# ── run_verify ────────────────────────────────────────────────────────────────

def test_verify_found(claude_json, capsys):
    with patch("builtins.input", return_value="y"):
        run_install(claude_json_path=claude_json)

    run_verify(claude_json_path=claude_json)

    out = capsys.readouterr().out
    assert "✓" in out
    assert "terminal-hub" in out


def test_verify_not_found_exits(claude_json):
    with pytest.raises(SystemExit):
        run_verify(claude_json_path=claude_json)
