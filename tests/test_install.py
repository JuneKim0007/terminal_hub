"""Tests for terminal-hub install command."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from terminal_hub.install import build_mcp_config, write_claude_json, read_claude_json


@pytest.fixture
def claude_json(tmp_path):
    path = tmp_path / ".claude.json"
    path.write_text(json.dumps({"projects": {}}))
    return path


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".git").mkdir()
    return tmp_path


# ── build_mcp_config ──────────────────────────────────────────────────────────

def test_build_config_with_repo(project):
    cfg = build_mcp_config(project, repo="owner/repo")
    assert cfg["args"] == ["-m", "terminal_hub"]
    assert cfg["env"]["PROJECT_ROOT"] == str(project)
    assert cfg["env"]["GITHUB_REPO"] == "owner/repo"


def test_build_config_without_repo(project):
    cfg = build_mcp_config(project, repo=None)
    assert "GITHUB_REPO" not in cfg["env"]
    assert cfg["env"]["PROJECT_ROOT"] == str(project)


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

def test_write_adds_mcp_entry(claude_json, project):
    cfg = build_mcp_config(project, repo="owner/repo")
    write_claude_json(claude_json, project, cfg)

    data = json.loads(claude_json.read_text())
    assert "terminal-hub" in data["projects"][str(project)]["mcpServers"]


def test_write_preserves_existing_projects(claude_json, project, tmp_path):
    other = tmp_path / "other"
    existing_data = {
        "projects": {
            str(other): {"mcpServers": {"some-other": {}}}
        }
    }
    claude_json.write_text(json.dumps(existing_data))

    cfg = build_mcp_config(project, repo=None)
    write_claude_json(claude_json, project, cfg)

    data = json.loads(claude_json.read_text())
    assert str(other) in data["projects"]
    assert str(project) in data["projects"]


def test_write_preserves_other_mcp_servers(claude_json, project):
    existing_data = {
        "projects": {
            str(project): {"mcpServers": {"other-server": {"command": "foo"}}}
        }
    }
    claude_json.write_text(json.dumps(existing_data))

    cfg = build_mcp_config(project, repo=None)
    write_claude_json(claude_json, project, cfg)

    data = json.loads(claude_json.read_text())
    servers = data["projects"][str(project)]["mcpServers"]
    assert "other-server" in servers
    assert "terminal-hub" in servers


def test_write_overwrites_existing_terminal_hub_entry(claude_json, project):
    old_data = {
        "projects": {
            str(project): {"mcpServers": {"terminal-hub": {"command": "old"}}}
        }
    }
    claude_json.write_text(json.dumps(old_data))

    cfg = build_mcp_config(project, repo="new/repo")
    write_claude_json(claude_json, project, cfg)

    data = json.loads(claude_json.read_text())
    entry = data["projects"][str(project)]["mcpServers"]["terminal-hub"]
    assert entry["env"]["GITHUB_REPO"] == "new/repo"
