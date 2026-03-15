from pathlib import Path
import pytest
from terminal_hub.config import load_config, save_config, WorkspaceMode


def test_save_and_load_local_config(tmp_path):
    (tmp_path / ".terminal_hub").mkdir()
    save_config(tmp_path, mode=WorkspaceMode.LOCAL, repo=None)
    cfg = load_config(tmp_path)
    assert cfg["mode"] == "local"
    assert cfg["repo"] is None


def test_save_and_load_github_config(tmp_path):
    (tmp_path / ".terminal_hub").mkdir()
    save_config(tmp_path, mode=WorkspaceMode.GITHUB, repo="owner/my-repo")
    cfg = load_config(tmp_path)
    assert cfg["mode"] == "github"
    assert cfg["repo"] == "owner/my-repo"


def test_load_config_returns_none_when_missing(tmp_path):
    assert load_config(tmp_path) is None


def test_workspace_mode_values():
    assert WorkspaceMode.LOCAL == "local"
    assert WorkspaceMode.GITHUB == "github"
