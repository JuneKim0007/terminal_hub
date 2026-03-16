"""Tests for install.py interactive flow."""
import json
from pathlib import Path
from unittest.mock import patch, call as mock_call
import pytest
from terminal_hub.install import run_install, _resolve_root, _resolve_repo, format_diff, build_mcp_config, _prompt


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".terminal_hub" / "issues").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def claude_json(tmp_path):
    path = tmp_path / ".claude.json"
    path.write_text(json.dumps({"projects": {}}))
    return path


# ── _prompt ───────────────────────────────────────────────────────────────────

def test_prompt_uses_default_on_empty_input():
    with patch("builtins.input", return_value=""):
        assert _prompt("Question", default="fallback") == "fallback"


def test_prompt_uses_user_input_over_default():
    with patch("builtins.input", return_value="typed"):
        assert _prompt("Question", default="fallback") == "typed"


# ── format_diff ───────────────────────────────────────────────────────────────

def test_format_diff_contains_project_root(project):
    cfg = build_mcp_config(project, "owner/repo")
    diff = format_diff(project, cfg)
    assert str(project) in diff
    assert "terminal-hub" in diff


# ── _resolve_root ─────────────────────────────────────────────────────────────

def test_resolve_root_uses_detected_root(project):
    with patch("terminal_hub.workspace.resolve_workspace_root", return_value=project):
        result = _resolve_root()
    assert result == project


def test_resolve_root_prompts_when_detection_fails(project):
    with patch("terminal_hub.workspace.resolve_workspace_root", return_value=None), \
         patch("builtins.input", return_value=str(project)):
        result = _resolve_root()
    assert result == project


def test_resolve_root_retries_on_invalid_path(project):
    with patch("terminal_hub.workspace.resolve_workspace_root", return_value=None), \
         patch("builtins.input", side_effect=["/nonexistent/path", str(project)]):
        result = _resolve_root()
    assert result == project


# ── _resolve_repo ─────────────────────────────────────────────────────────────

def test_resolve_repo_uses_detected_repo(project):
    with patch("terminal_hub.workspace.detect_repo", return_value="owner/repo"):
        result = _resolve_repo(project)
    assert result == "owner/repo"


def test_resolve_repo_prompts_when_not_detected(project):
    with patch("terminal_hub.workspace.detect_repo", return_value=None), \
         patch("builtins.input", return_value="owner/my-repo"):
        result = _resolve_repo(project)
    assert result == "owner/my-repo"


def test_resolve_repo_returns_none_on_blank_input(project):
    with patch("terminal_hub.workspace.detect_repo", return_value=None), \
         patch("builtins.input", return_value=""):
        result = _resolve_repo(project)
    assert result is None


# ── run_install ───────────────────────────────────────────────────────────────

def test_run_install_writes_claude_json(project, claude_json):
    with patch("terminal_hub.install._resolve_root", return_value=project), \
         patch("terminal_hub.install._resolve_repo", return_value="owner/repo"), \
         patch("builtins.input", return_value="y"):
        run_install(claude_json_path=claude_json)

    data = json.loads(claude_json.read_text())
    assert "terminal-hub" in data["projects"][str(project)]["mcpServers"]


def test_run_install_writes_env_file(project, claude_json):
    with patch("terminal_hub.install._resolve_root", return_value=project), \
         patch("terminal_hub.install._resolve_repo", return_value="owner/repo"), \
         patch("builtins.input", return_value="y"):
        run_install(claude_json_path=claude_json)

    from terminal_hub.env_store import read_env
    env = read_env(project)
    assert env["PROJECT_ROOT"] == str(project)
    assert env["GITHUB_REPO"] == "owner/repo"


def test_run_install_aborts_on_no(project, claude_json):
    with patch("terminal_hub.install._resolve_root", return_value=project), \
         patch("terminal_hub.install._resolve_repo", return_value=None), \
         patch("builtins.input", return_value="n"), \
         pytest.raises(SystemExit):
        run_install(claude_json_path=claude_json)

    data = json.loads(claude_json.read_text())
    assert "terminal-hub" not in data.get("projects", {}).get(str(project), {}).get("mcpServers", {})


def test_run_install_gitignores_env(project, claude_json):
    with patch("terminal_hub.install._resolve_root", return_value=project), \
         patch("terminal_hub.install._resolve_repo", return_value=None), \
         patch("builtins.input", return_value="y"):
        run_install(claude_json_path=claude_json)

    assert ".terminal_hub/.env" in (project / ".gitignore").read_text()
