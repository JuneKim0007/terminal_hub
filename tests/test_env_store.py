from pathlib import Path
import pytest
from terminal_hub.env_store import read_env, write_env


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".terminal_hub").mkdir()
    return tmp_path


def test_read_env_missing_file_returns_empty(workspace):
    assert read_env(workspace) == {}


def test_write_and_read_back(workspace):
    write_env(workspace, {"PROJECT_ROOT": "/my/project", "GITHUB_REPO": "owner/repo"})
    result = read_env(workspace)
    assert result["PROJECT_ROOT"] == "/my/project"
    assert result["GITHUB_REPO"] == "owner/repo"


def test_write_merges_with_existing(workspace):
    write_env(workspace, {"PROJECT_ROOT": "/my/project"})
    write_env(workspace, {"GITHUB_REPO": "owner/repo"})
    result = read_env(workspace)
    assert result["PROJECT_ROOT"] == "/my/project"
    assert result["GITHUB_REPO"] == "owner/repo"


def test_write_updates_existing_key(workspace):
    write_env(workspace, {"PROJECT_ROOT": "/old"})
    write_env(workspace, {"PROJECT_ROOT": "/new"})
    assert read_env(workspace)["PROJECT_ROOT"] == "/new"


def test_write_skips_empty_values(workspace):
    write_env(workspace, {"PROJECT_ROOT": "/my/project", "GITHUB_TOKEN": ""})
    result = read_env(workspace)
    assert "GITHUB_TOKEN" not in result


def test_read_ignores_comments_and_blank_lines(workspace):
    env_file = workspace / ".terminal_hub" / ".env"
    env_file.write_text("# comment\n\nPROJECT_ROOT=/my/project\n")
    result = read_env(workspace)
    assert result == {"PROJECT_ROOT": "/my/project"}


def test_write_auto_adds_to_gitignore(workspace):
    (workspace / ".gitignore").write_text("*.pyc\n")
    write_env(workspace, {"PROJECT_ROOT": "/x"})
    content = (workspace / ".gitignore").read_text()
    assert ".terminal_hub/.env" in content


def test_write_creates_gitignore_if_missing(workspace):
    write_env(workspace, {"PROJECT_ROOT": "/x"})
    assert (workspace / ".gitignore").exists()
    assert ".terminal_hub/.env" in (workspace / ".gitignore").read_text()


def test_write_does_not_duplicate_gitignore_entry(workspace):
    (workspace / ".gitignore").write_text(".terminal_hub/.env\n")
    write_env(workspace, {"PROJECT_ROOT": "/x"})
    content = (workspace / ".gitignore").read_text()
    assert content.count(".terminal_hub/.env") == 1
