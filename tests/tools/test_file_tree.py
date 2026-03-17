"""Tests for get_file_tree tool and _do_get_file_tree / _build_file_tree helpers."""
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from extensions.github_planner import (
    _FILE_TREE_CACHE,
    _build_file_tree,
    _do_get_file_tree,
    _file_tree_cache_path,
    _should_ignore,
)
from terminal_hub.server import create_server


def call(server, tool_name, args=None):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args or {}))


@pytest.fixture(autouse=True)
def clear_cache():
    _FILE_TREE_CACHE.clear()
    yield
    _FILE_TREE_CACHE.clear()


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    (tmp_path / "hub_agents" / "config.yaml").write_text("mode: local\n")
    return tmp_path


@pytest.fixture
def populated(tmp_path):
    """Workspace with a few files and directories."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("# main")
    (tmp_path / "src" / "utils.py").write_text("# utils")
    (tmp_path / "README.md").write_text("# Readme")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-311.pyc").write_text("bytecode")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main")
    (tmp_path / "venv").mkdir()
    (tmp_path / "venv" / "pyvenv.cfg").write_text("")
    return tmp_path


# ── _should_ignore ────────────────────────────────────────────────────────────

def test_should_ignore_git():
    assert _should_ignore(".git") is True


def test_should_ignore_pycache():
    assert _should_ignore("__pycache__") is True


def test_should_ignore_venv():
    assert _should_ignore("venv") is True


def test_should_ignore_egg_info():
    assert _should_ignore("mypackage.egg-info") is True


def test_should_ignore_normal_dir():
    assert _should_ignore("src") is False


def test_should_ignore_normal_file():
    assert _should_ignore("main.py") is False


# ── _build_file_tree ──────────────────────────────────────────────────────────

def test_build_file_tree_excludes_ignored(populated):
    tree, flat = _build_file_tree(populated)
    assert "__pycache__/" not in tree
    assert ".git/" not in tree
    assert "venv/" not in tree


def test_build_file_tree_includes_src(populated):
    tree, flat = _build_file_tree(populated)
    assert "src/" in tree
    assert "README.md" in tree


def test_build_file_tree_flat_index(populated):
    _, flat = _build_file_tree(populated)
    assert "README.md" in flat
    assert "src/main.py" in flat
    assert "src/utils.py" in flat


def test_build_file_tree_no_ignored_in_flat(populated):
    _, flat = _build_file_tree(populated)
    for path in flat:
        parts = Path(path).parts
        for part in parts:
            assert not _should_ignore(part), f"{path!r} should have been excluded"


# ── _do_get_file_tree ─────────────────────────────────────────────────────────

def test_do_get_file_tree_returns_tree(populated):
    with patch("extensions.github_planner.get_workspace_root", return_value=populated):
        result = _do_get_file_tree()
    assert "tree" in result
    assert "flat_index" in result
    assert result["total_files"] > 0


def test_do_get_file_tree_writes_disk_cache(populated):
    with patch("extensions.github_planner.get_workspace_root", return_value=populated):
        _do_get_file_tree()
    assert _file_tree_cache_path(populated).exists()


def test_do_get_file_tree_uses_memory_cache(populated):
    with patch("extensions.github_planner.get_workspace_root", return_value=populated):
        r1 = _do_get_file_tree()
        # Delete the disk cache — second call must still succeed from memory
        _file_tree_cache_path(populated).unlink()
        r2 = _do_get_file_tree()
    assert r1["fetched_at"] == r2["fetched_at"]


def test_do_get_file_tree_refresh_bypasses_cache(populated):
    with patch("extensions.github_planner.get_workspace_root", return_value=populated):
        r1 = _do_get_file_tree()
        # Poison in-memory cache with a fake timestamp so we can detect if refresh ignores it
        _FILE_TREE_CACHE["fetched_at"] = "2000-01-01T00:00:00+00:00"
        r2 = _do_get_file_tree(refresh=True)
    # refresh=True must produce a fresh tree, not the poisoned 2000 timestamp
    assert r2["fetched_at"] != "2000-01-01T00:00:00+00:00"


def test_do_get_file_tree_reads_disk_cache_when_memory_empty(populated):
    with patch("extensions.github_planner.get_workspace_root", return_value=populated):
        r1 = _do_get_file_tree()
        _FILE_TREE_CACHE.clear()
        r2 = _do_get_file_tree()
    assert r1["fetched_at"] == r2["fetched_at"]


# ── MCP tool registration ─────────────────────────────────────────────────────

def test_get_file_tree_tool_registered(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
    names = {t.name for t in server._tool_manager.list_tools()}
    assert "get_file_tree" in names


def test_get_file_tree_tool_returns_tree(populated):
    (populated / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)
    (populated / "hub_agents" / "config.yaml").write_text("mode: local\n")
    with patch("extensions.github_planner.get_workspace_root", return_value=populated):
        server = create_server()
        result = call(server, "get_file_tree", {})
    assert "flat_index" in result
    assert result["total_files"] > 0
