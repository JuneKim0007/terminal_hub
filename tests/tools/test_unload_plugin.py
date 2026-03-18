"""Tests for list_plugin_state and unload_plugin tools."""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from extensions.github_planner import (
    _ANALYSIS_CACHE,
    _FILE_TREE_CACHE,
    _GH_PLANNER_VOLATILE_FILES,
    _PROJECT_DOCS_CACHE,
    _SESSION_HEADER_CACHE,
    _do_list_plugin_state,
    _do_unload_plugin,
    _gh_planner_docs_dir,
)
from terminal_hub.server import create_server


def call(server, tool_name, args=None):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args or {}))


@pytest.fixture(autouse=True)
def clear_caches():
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    _FILE_TREE_CACHE.clear()
    _SESSION_HEADER_CACHE.clear()
    yield
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    _FILE_TREE_CACHE.clear()
    _SESSION_HEADER_CACHE.clear()


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    (tmp_path / "hub_agents" / "config.yaml").write_text("mode: local\n")
    return tmp_path


def _write_volatile_files(workspace: Path) -> list[Path]:
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for fname in _GH_PLANNER_VOLATILE_FILES:
        p = docs_dir / fname
        p.write_text("{}")
        written.append(p)
    return written


# ── _do_list_plugin_state ─────────────────────────────────────────────────────

def test_list_plugin_state_empty_when_nothing_loaded(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_plugin_state("gh_planner")
    assert result["total_caches"] == 0
    assert result["total_disk_files"] == 0


def test_list_plugin_state_reports_in_memory_caches(workspace):
    _ANALYSIS_CACHE["o/r"] = {"repo": "o/r"}
    _FILE_TREE_CACHE["tree"] = {}
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_plugin_state("gh_planner")
    cache_names = [c["name"] for c in result["caches"]]
    assert "_ANALYSIS_CACHE" in cache_names
    assert "_FILE_TREE_CACHE" in cache_names


def test_list_plugin_state_reports_disk_files(workspace):
    _write_volatile_files(workspace)
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_plugin_state("gh_planner")
    assert result["total_disk_files"] == len(_GH_PLANNER_VOLATILE_FILES)


def test_list_plugin_state_unknown_plugin_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_plugin_state("nonexistent")
    assert result["error"] == "unknown_plugin"


def test_list_plugin_state_has_display(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_plugin_state("gh_planner")
    assert "_display" in result
    assert "gh_planner" in result["_display"]


# ── _do_unload_plugin ─────────────────────────────────────────────────────────

def test_unload_plugin_clears_in_memory_caches(workspace):
    _ANALYSIS_CACHE["o/r"] = {}
    _PROJECT_DOCS_CACHE["o/r"] = {}
    _FILE_TREE_CACHE["tree"] = {}
    _SESSION_HEADER_CACHE["docs"] = True
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_unload_plugin("gh_planner")
    assert result["success"] is True
    assert len(_ANALYSIS_CACHE) == 0
    assert len(_PROJECT_DOCS_CACHE) == 0
    assert len(_FILE_TREE_CACHE) == 0
    assert len(_SESSION_HEADER_CACHE) == 0


def test_unload_plugin_removes_volatile_files(workspace):
    written = _write_volatile_files(workspace)
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_unload_plugin("gh_planner")
    assert result["success"] is True
    for p in written:
        assert not p.exists()


def test_unload_plugin_preserves_project_docs(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True, exist_ok=True)
    summary = docs_dir / "project_summary.md"
    detail = docs_dir / "project_detail.md"
    summary.write_text("# My Project")
    detail.write_text("## Auth\nrules")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        _do_unload_plugin("gh_planner")
    assert summary.exists()
    assert detail.exists()


def test_unload_plugin_preserves_issues(workspace):
    (workspace / "hub_agents" / "issues" / "test.md").write_text("---\ntitle: T\n---")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        _do_unload_plugin("gh_planner")
    assert (workspace / "hub_agents" / "issues" / "test.md").exists()


def test_unload_plugin_success_display(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_unload_plugin("gh_planner")
    assert result["success"] is True
    assert result["_display"] == "Unloading successful!"


def test_unload_plugin_unknown_plugin_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_unload_plugin("nonexistent")
    assert result["error"] == "unknown_plugin"


def test_unload_plugin_lists_cleared_items(workspace):
    _ANALYSIS_CACHE["o/r"] = {}
    _write_volatile_files(workspace)
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_unload_plugin("gh_planner")
    assert "_ANALYSIS_CACHE" in result["cleared"]
    assert len([c for c in result["cleared"] if c.endswith(".json")]) == len(_GH_PLANNER_VOLATILE_FILES)


# ── MCP tool registration ─────────────────────────────────────────────────────

def test_list_plugin_state_tool_registered(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
    names = {t.name for t in server._tool_manager.list_tools()}
    assert "list_plugin_state" in names


def test_unload_plugin_tool_registered(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
    names = {t.name for t in server._tool_manager.list_tools()}
    assert "unload_plugin" in names


def test_unload_plugin_tool_returns_success(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "unload_plugin", {"plugin": "gh_planner"})
    assert result["success"] is True
    assert "Unloading successful!" in result["_display"]


def test_list_plugin_state_dict_size_kb_exception(workspace):
    """_dict_size_kb returns 0 when sys.getsizeof raises (lines 1865-1866)."""
    import sys as _sys
    _ANALYSIS_CACHE["o/r"] = {"data": "x"}
    try:
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("sys.getsizeof", side_effect=Exception("getsizeof failed")):
            result = _do_list_plugin_state("gh_planner")
        # Should not crash; estimated_memory_kb should be 0
        assert result["estimated_memory_kb"] == 0
    finally:
        _ANALYSIS_CACHE.clear()
