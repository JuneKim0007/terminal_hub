"""Tests for scan profile functionality (#149).

Covers:
- _load_scan_profile fallback to defaults when file absent
- _load_scan_profile returning custom values when file present
- _do_analyze_repo_full respecting max_files from profile
- _do_get_scan_profile_status returning needs_creation when absent
- _do_get_scan_profile_status returning exists=True when present
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from extensions.github_planner import (
    _ANALYSIS_CACHE,
    _DEFAULT_SCAN_PROFILE,
    _FILE_TREE_CACHE,
    _do_analyze_repo_full,
    _do_get_scan_profile_status,
    _do_create_scan_profile,
    _gh_planner_docs_dir,
    _load_scan_profile,
    _scan_profile_path,
    _build_file_tree,
    _should_ignore,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_caches():
    _ANALYSIS_CACHE.clear()
    _FILE_TREE_CACHE.clear()
    yield
    _ANALYSIS_CACHE.clear()
    _FILE_TREE_CACHE.clear()


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


# ── _load_scan_profile ────────────────────────────────────────────────────────

def test_scan_profile_defaults_when_missing(workspace):
    """No scan_profile.yaml → returns default profile."""
    profile = _load_scan_profile(workspace)
    assert profile["include_extensions"] == _DEFAULT_SCAN_PROFILE["include_extensions"]
    assert profile["max_files"] == _DEFAULT_SCAN_PROFILE["max_files"]
    assert "node_modules" in profile["exclude_dirs"]


def test_scan_profile_loaded_from_disk(workspace):
    """Write a custom yaml, load it → custom values returned."""
    import yaml
    custom = {
        "include_extensions": [".py", ".md"],
        "exclude_dirs": ["dist"],
        "exclude_patterns": ["*.lock"],
        "max_files": 42,
    }
    profile_path = _scan_profile_path(workspace)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(yaml.dump(custom), encoding="utf-8")

    loaded = _load_scan_profile(workspace)
    assert loaded["max_files"] == 42
    assert loaded["include_extensions"] == [".py", ".md"]
    assert loaded["exclude_dirs"] == ["dist"]


def test_scan_profile_merges_missing_keys(workspace):
    """Partial yaml: missing keys are filled from defaults."""
    import yaml
    partial = {"max_files": 50}
    profile_path = _scan_profile_path(workspace)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(yaml.dump(partial), encoding="utf-8")

    loaded = _load_scan_profile(workspace)
    assert loaded["max_files"] == 50
    # Missing keys should come from defaults
    assert "include_extensions" in loaded
    assert len(loaded["include_extensions"]) > 0


def test_scan_profile_falls_back_on_invalid_yaml(workspace):
    """Corrupt yaml → returns default profile."""
    profile_path = _scan_profile_path(workspace)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text("{{{{INVALID YAML{{{{", encoding="utf-8")

    loaded = _load_scan_profile(workspace)
    assert loaded == _DEFAULT_SCAN_PROFILE


# ── _do_analyze_repo_full respects max_files ──────────────────────────────────

def _make_tree_with_sha(entries):
    return [{"path": p, "size": 100, "sha": sha} for p, sha in entries]


def test_analyze_respects_max_files_from_profile(workspace):
    """Profile with max_files=5, directory with 10 .py files → only 5 analyzed."""
    import yaml

    # Write a profile with max_files=5
    profile_path = _scan_profile_path(workspace)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(yaml.dump({
        "include_extensions": [".py"],
        "exclude_dirs": [],
        "exclude_patterns": [],
        "max_files": 5,
    }), encoding="utf-8")

    # Build a 10-file tree
    entries = [(f"src/file{i}.py", f"sha{i}") for i in range(10)]
    tree = _make_tree_with_sha(entries)

    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_repo_tree.return_value = tree
    mock_gh.get_file_content.return_value = "def f(): pass"

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_analyze_repo_full("o/r")

    # total_files is the capped tree length (5), not the raw count
    assert result["total_files"] <= 5
    # omitted_files should reflect that 5 were omitted
    assert result["omitted_files"] == 5


# ── _do_get_scan_profile_status ───────────────────────────────────────────────

def test_get_scan_profile_status_missing(workspace):
    """File absent → needs_creation: True."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_scan_profile_status()

    assert result["exists"] is False
    assert result["needs_creation"] is True
    assert "default_content" in result
    assert "_display" in result


def test_get_scan_profile_status_present(workspace):
    """File present → exists: True."""
    import yaml
    profile_path = _scan_profile_path(workspace)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(yaml.dump(_DEFAULT_SCAN_PROFILE), encoding="utf-8")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_scan_profile_status()

    assert result["exists"] is True
    assert "needs_creation" not in result or result.get("needs_creation") is False
    assert "profile" in result


# ── _do_create_scan_profile ───────────────────────────────────────────────────

def test_create_scan_profile_writes_default(workspace):
    """create_scan_profile(content=None) writes default yaml."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_create_scan_profile(content=None)

    assert result["created"] is True
    profile_path = _scan_profile_path(workspace)
    assert profile_path.exists()
    text = profile_path.read_text()
    assert "include_extensions" in text


def test_create_scan_profile_writes_custom(workspace):
    """create_scan_profile(content=...) writes the given content."""
    custom_yaml = "max_files: 99\ninclude_extensions: [.py]\nexclude_dirs: []\nexclude_patterns: []\n"
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_create_scan_profile(content=custom_yaml)

    assert result["created"] is True
    profile_path = _scan_profile_path(workspace)
    assert profile_path.read_text() == custom_yaml


# ── _should_ignore with extra_exclude_dirs ───────────────────────────────────

def test_should_ignore_builtin():
    """Built-in ignores still work with no extra dirs."""
    assert _should_ignore("node_modules") is True
    assert _should_ignore(".git") is True
    assert _should_ignore("src") is False


def test_should_ignore_extra_dirs():
    """Extra exclude dirs from profile are respected."""
    assert _should_ignore("my_custom_dir", frozenset({"my_custom_dir"})) is True
    assert _should_ignore("other_dir", frozenset({"my_custom_dir"})) is False


# ── _build_file_tree with profile exclude_dirs ────────────────────────────────

def test_build_file_tree_excludes_profile_dirs(tmp_path):
    """_build_file_tree respects extra_exclude_dirs from scan profile."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("code")
    (tmp_path / "secret_stuff").mkdir()
    (tmp_path / "secret_stuff" / "data.py").write_text("data")

    _, flat = _build_file_tree(tmp_path, extra_exclude_dirs=frozenset({"secret_stuff"}))
    assert any("main.py" in p for p in flat)
    assert not any("secret_stuff" in p for p in flat)
