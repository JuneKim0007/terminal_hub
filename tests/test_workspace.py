import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import terminal_hub.workspace as _ws_mod
from terminal_hub.workspace import detect_repo, init_workspace, set_active_project_root, resolve_workspace_root


def test_init_workspace_creates_directories(tmp_path):
    init_workspace(tmp_path)
    assert (tmp_path / "hub_agents").is_dir()
    assert (tmp_path / "hub_agents" / "issues").is_dir()


def test_init_workspace_is_idempotent(tmp_path):
    init_workspace(tmp_path)
    init_workspace(tmp_path)
    assert (tmp_path / "hub_agents").is_dir()


def test_detect_repo_from_env(tmp_path):
    with patch.dict("os.environ", {"GITHUB_REPO": "owner/my-repo"}):
        assert detect_repo(tmp_path) == "owner/my-repo"


def test_detect_repo_from_git_remote(tmp_path):
    with patch("subprocess.check_output", return_value=b"git@github.com:owner/repo.git\n"):
        assert detect_repo(tmp_path) == "owner/repo"


def test_detect_repo_returns_none_when_no_remote(tmp_path):
    with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "git")):
        with patch.dict("os.environ", {}, clear=True):
            assert detect_repo(tmp_path) is None


def test_detect_repo_parses_https_remote(tmp_path):
    with patch("subprocess.check_output", return_value=b"https://github.com/owner/repo.git\n"):
        assert detect_repo(tmp_path) == "owner/repo"


def test_set_active_project_root_overrides_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr(_ws_mod, "_ACTIVE_PROJECT_ROOT", None)
    set_active_project_root(tmp_path)
    assert resolve_workspace_root() == tmp_path.resolve()
    monkeypatch.setattr(_ws_mod, "_ACTIVE_PROJECT_ROOT", None)


def test_set_project_root_resets(tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setattr(_ws_mod, "_ACTIVE_PROJECT_ROOT", None)
    set_active_project_root(tmp_path)
    assert resolve_workspace_root() == tmp_path.resolve()
    set_active_project_root(other)
    assert resolve_workspace_root() == other.resolve()
    monkeypatch.setattr(_ws_mod, "_ACTIVE_PROJECT_ROOT", None)
