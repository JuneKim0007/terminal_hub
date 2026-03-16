import os
from pathlib import Path
from unittest.mock import patch
import pytest
from terminal_hub.workspace import resolve_workspace_root, is_valid_project


@pytest.fixture
def git_project(tmp_path):
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture
def hub_project(tmp_path):
    (tmp_path / "hub_agents").mkdir()
    return tmp_path


# ── is_valid_project ──────────────────────────────────────────────────────────

def test_valid_if_has_git(git_project):
    assert is_valid_project(git_project) is True


def test_valid_if_has_hub_agents(hub_project):
    assert is_valid_project(hub_project) is True


def test_invalid_if_empty(tmp_path):
    assert is_valid_project(tmp_path) is False


# ── resolve_workspace_root ────────────────────────────────────────────────────

def test_env_var_takes_priority(git_project):
    with patch.dict(os.environ, {"PROJECT_ROOT": str(git_project)}):
        assert resolve_workspace_root() == git_project


def test_returns_cwd_when_no_env_var(tmp_path):
    with patch.dict(os.environ, {}, clear=True), \
         patch("terminal_hub.workspace._cwd", return_value=tmp_path):
        result = resolve_workspace_root()
    assert result == tmp_path


def test_cwd_used_when_valid(git_project):
    with patch.dict(os.environ, {}, clear=True), \
         patch("terminal_hub.workspace._cwd", return_value=git_project):
        result = resolve_workspace_root()
    assert result == git_project
