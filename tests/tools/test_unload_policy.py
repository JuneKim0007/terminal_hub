"""Tests for apply_unload_policy MCP tool and unload_policy.json."""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from terminal_hub.server import create_server


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


# ── unload_policy.json structure ──────────────────────────────────────────────

def test_unload_policy_json_is_valid():
    policy_path = Path(__file__).parent.parent.parent / "extensions" / "github_planner" / "unload_policy.json"
    data = json.loads(policy_path.read_text())
    assert "commands" in data
    assert "cache_keys" in data
    assert "always_keep" in data


def test_every_command_has_unload_and_keep():
    policy_path = Path(__file__).parent.parent.parent / "extensions" / "github_planner" / "unload_policy.json"
    data = json.loads(policy_path.read_text())
    for name, entry in data["commands"].items():
        assert "unload" in entry, f"Command {name!r} missing 'unload'"
        assert "keep" in entry, f"Command {name!r} missing 'keep'"
        assert isinstance(entry["unload"], list), f"Command {name!r} unload must be a list"
        assert isinstance(entry["keep"], list), f"Command {name!r} keep must be a list"


def test_unload_keys_are_known_cache_keys():
    policy_path = Path(__file__).parent.parent.parent / "extensions" / "github_planner" / "unload_policy.json"
    data = json.loads(policy_path.read_text())
    known_keys = set(data["cache_keys"].keys())
    for name, entry in data["commands"].items():
        for key in entry["unload"]:
            assert key in known_keys, f"Command {name!r} unloads unknown key {key!r}"


def test_github_planner_command_unloads_analysis_keeps_repo():
    policy_path = Path(__file__).parent.parent.parent / "extensions" / "github_planner" / "unload_policy.json"
    data = json.loads(policy_path.read_text())
    cmd = data["commands"]["github-planner"]
    assert "analysis_cache" in cmd["unload"]
    assert "repo_cache" in cmd["keep"] or "github_repo" in cmd["keep"]


def test_github_repo_creation_keeps_repo_cache():
    policy_path = Path(__file__).parent.parent.parent / "extensions" / "github_planner" / "unload_policy.json"
    data = json.loads(policy_path.read_text())
    cmd = data["commands"]["create-github-repo"]
    assert "repo_cache" in cmd["keep"]
    assert "github_repo" in cmd["keep"]


# ── apply_unload_policy MCP tool ──────────────────────────────────────────────

def test_apply_unload_policy_success(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "apply_unload_policy", {"command": "github-planner/list-issues"})
    assert result["success"] is True
    assert result["command"] == "github-planner/list-issues"
    assert isinstance(result["cleared"], list)
    assert isinstance(result["kept"], list)
    assert "_display" in result


def test_apply_unload_policy_clears_in_memory_cache(workspace):
    from extensions.github_planner import _ANALYSIS_CACHE
    _ANALYSIS_CACHE["owner/repo"] = {"fake": True}

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "apply_unload_policy", {"command": "github-planner"})

    assert len(_ANALYSIS_CACHE) == 0


def test_apply_unload_policy_deletes_disk_file(workspace):
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    docs_dir.mkdir(parents=True)
    snapshot = docs_dir / "analyzer_snapshot.json"
    snapshot.write_text("{}")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "apply_unload_policy", {"command": "github-planner"})

    assert not snapshot.exists()
    assert "analyzer_snapshot.json" in result["cleared"]


def test_apply_unload_policy_preserves_kept_cache(workspace):
    from extensions.github_planner import _PROJECT_DOCS_CACHE
    _PROJECT_DOCS_CACHE["key"] = {"doc": "data"}

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        # create-issue only unloads session_header_cache, keeps project_docs_cache
        call(server, "apply_unload_policy", {"command": "github-planner/create-issue"})

    # project_docs_cache should still have data
    assert "key" in _PROJECT_DOCS_CACHE
    _PROJECT_DOCS_CACHE.clear()  # cleanup


def test_apply_unload_policy_unknown_command_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "apply_unload_policy", {"command": "nonexistent-command"})
    assert result["error"] == "unknown_command"
    assert result["_hook"] is None


def test_apply_unload_policy_not_initialized_returns_needs_init(tmp_path):
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "apply_unload_policy", {"command": "github-planner"})
    assert result["status"] == "needs_init"


def test_apply_unload_policy_display_contains_command(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "apply_unload_policy", {"command": "current-stat"})
    assert "current-stat" in result["_display"]


def test_apply_unload_policy_policy_load_failure(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._load_unload_policy", return_value={"error": "file missing", "commands": {}}):
        server = create_server()
        result = call(server, "apply_unload_policy", {"command": "github-planner"})
    assert result["error"] == "policy_load_failed"
    assert result["_hook"] is None


def test_apply_unload_policy_oserror_on_unlink(workspace):
    from unittest.mock import MagicMock
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    docs_dir.mkdir(parents=True)
    snapshot = docs_dir / "analyzer_snapshot.json"
    snapshot.write_text("{}")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("pathlib.Path.unlink", side_effect=OSError("permission denied")):
        server = create_server()
        result = call(server, "apply_unload_policy", {"command": "github-planner"})

    assert result["success"] is False
    assert any("permission denied" in e for e in result["errors"])
