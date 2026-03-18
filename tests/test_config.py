from pathlib import Path
import pytest
from terminal_hub.config import load_config, save_config, read_preference, write_preference, WorkspaceMode


def test_save_and_load_local_config(tmp_path):
    (tmp_path / "hub_agents").mkdir()
    save_config(tmp_path, mode=WorkspaceMode.LOCAL, repo=None)
    cfg = load_config(tmp_path)
    assert cfg["mode"] == "local"
    assert cfg["repo"] is None


def test_save_and_load_github_config(tmp_path):
    (tmp_path / "hub_agents").mkdir()
    save_config(tmp_path, mode=WorkspaceMode.GITHUB, repo="owner/my-repo")
    cfg = load_config(tmp_path)
    assert cfg["mode"] == "github"
    assert cfg["repo"] == "owner/my-repo"


def test_load_config_returns_none_when_missing(tmp_path):
    assert load_config(tmp_path) is None


def test_workspace_mode_values():
    assert WorkspaceMode.LOCAL == "local"
    assert WorkspaceMode.GITHUB == "github"


def test_save_config_preserves_existing_preferences(tmp_path):
    (tmp_path / "hub_agents").mkdir()
    write_preference(tmp_path, "confirm_arch_changes", True)
    save_config(tmp_path, mode=WorkspaceMode.LOCAL, repo=None)
    assert read_preference(tmp_path, "confirm_arch_changes") is True


def test_read_preference_returns_default_when_missing(tmp_path):
    assert read_preference(tmp_path, "confirm_arch_changes", default=None) is None


def test_write_and_read_preference_bool(tmp_path):
    write_preference(tmp_path, "confirm_arch_changes", False)
    assert read_preference(tmp_path, "confirm_arch_changes") is False
    write_preference(tmp_path, "confirm_arch_changes", True)
    assert read_preference(tmp_path, "confirm_arch_changes") is True


def test_write_preference_creates_config_if_missing(tmp_path):
    assert not (tmp_path / "hub_agents" / "config.yaml").exists()
    write_preference(tmp_path, "confirm_arch_changes", True)
    assert (tmp_path / "hub_agents" / "config.yaml").exists()
    assert read_preference(tmp_path, "confirm_arch_changes") is True
