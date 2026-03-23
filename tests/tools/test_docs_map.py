"""Tests for build_docs_map and get_docs_map MCP tools."""
import asyncio
import json
import textwrap
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


@pytest.fixture
def plugin_dir(tmp_path):
    """Minimal plugin directory with one skill and one command."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    # Skill file
    (skills_dir / "my_skill.md").write_text(
        textwrap.dedent("""\
        ---
        name: my_skill
        alwaysApply: false
        triggers:
          - do the thing
          - run my skill
        ---
        # my_skill
        """),
        encoding="utf-8",
    )

    # Always-apply skill
    (skills_dir / "always_skill.md").write_text(
        textwrap.dedent("""\
        ---
        name: always_skill
        alwaysApply: true
        ---
        # always_skill
        """),
        encoding="utf-8",
    )

    # SKILLS.md (should be ignored)
    (skills_dir / "SKILLS.md").write_text("# registry\n", encoding="utf-8")

    # Command file that loads my_skill
    (commands_dir / "my-cmd.md").write_text(
        textwrap.dedent("""\
        # /th:my-cmd
        Call `load_skill("my_skill")` to load knowledge.
        Then call `draft_issue(title, body)` to create an issue.
        """),
        encoding="utf-8",
    )

    # Command file with no skill refs
    (commands_dir / "bare-cmd.md").write_text(
        "# /th:bare-cmd\nJust call `list_issues()`.\n",
        encoding="utf-8",
    )

    return tmp_path


def test_build_docs_map_skills(plugin_dir, workspace):
    with (
        patch("extensions.gh_management.github_planner._PLUGIN_DIR", plugin_dir),
        patch("extensions.gh_management.github_planner._COMMANDS_DIR", plugin_dir / "commands"),
        patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace),
    ):
        server = create_server()
        result = call(server, "build_docs_map", {})

    assert "skills" in result
    assert "my_skill" in result["skills"]
    assert result["skills"]["my_skill"]["alwaysApply"] is False
    assert "do the thing" in result["skills"]["my_skill"]["triggers"]
    assert "always_skill" in result["skills"]
    assert result["skills"]["always_skill"]["alwaysApply"] is True
    # SKILLS.md must not appear
    assert "SKILLS" not in result["skills"]


def test_build_docs_map_command_skill_backlink(plugin_dir, workspace):
    with (
        patch("extensions.gh_management.github_planner._PLUGIN_DIR", plugin_dir),
        patch("extensions.gh_management.github_planner._COMMANDS_DIR", plugin_dir / "commands"),
        patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace),
    ):
        server = create_server()
        result = call(server, "build_docs_map", {})

    # my-cmd.md loads my_skill → back-linked
    assert "my-cmd.md" in result["skills"]["my_skill"]["used_by_commands"]
    # bare-cmd.md loads nothing → my_skill not back-linked from it
    assert "bare-cmd.md" not in result["skills"]["my_skill"]["used_by_commands"]


def test_build_docs_map_commands(plugin_dir, workspace):
    with (
        patch("extensions.gh_management.github_planner._PLUGIN_DIR", plugin_dir),
        patch("extensions.gh_management.github_planner._COMMANDS_DIR", plugin_dir / "commands"),
        patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace),
    ):
        server = create_server()
        result = call(server, "build_docs_map", {})

    assert "my-cmd.md" in result["commands"]
    assert "my_skill" in result["commands"]["my-cmd.md"]["loads_skills"]
    assert result["commands"]["my-cmd.md"]["entry_point"] == "/th:my-cmd"
    assert "bare-cmd.md" in result["commands"]
    assert result["commands"]["bare-cmd.md"]["loads_skills"] == []


def test_build_docs_map_writes_json(plugin_dir, workspace):
    with (
        patch("extensions.gh_management.github_planner._PLUGIN_DIR", plugin_dir),
        patch("extensions.gh_management.github_planner._COMMANDS_DIR", plugin_dir / "commands"),
        patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace),
    ):
        server = create_server()
        call(server, "build_docs_map", {})

    map_path = plugin_dir / "docs_map.json"
    assert map_path.exists()
    data = json.loads(map_path.read_text(encoding="utf-8"))
    assert "skills" in data
    assert "commands" in data


def test_get_docs_map_skills_view(plugin_dir, workspace):
    with (
        patch("extensions.gh_management.github_planner._PLUGIN_DIR", plugin_dir),
        patch("extensions.gh_management.github_planner._COMMANDS_DIR", plugin_dir / "commands"),
        patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace),
    ):
        server = create_server()
        call(server, "build_docs_map", {})
        result = call(server, "get_docs_map", {"view": "skills"})

    assert result["view"] == "skills"
    assert "Skill Map" in result["_display"]
    assert "my_skill" in result["_display"]
    assert "always_skill" in result["_display"]


def test_get_docs_map_commands_view(plugin_dir, workspace):
    with (
        patch("extensions.gh_management.github_planner._PLUGIN_DIR", plugin_dir),
        patch("extensions.gh_management.github_planner._COMMANDS_DIR", plugin_dir / "commands"),
        patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace),
    ):
        server = create_server()
        call(server, "build_docs_map", {})
        result = call(server, "get_docs_map", {"view": "commands"})

    assert result["view"] == "commands"
    assert "Command Map" in result["_display"]
    assert "my-cmd.md" in result["_display"]


def test_get_docs_map_auto_builds_if_missing(plugin_dir, workspace):
    """get_docs_map should rebuild docs_map.json if the file is absent."""
    map_path = plugin_dir / "docs_map.json"
    assert not map_path.exists()

    with (
        patch("extensions.gh_management.github_planner._PLUGIN_DIR", plugin_dir),
        patch("extensions.gh_management.github_planner._COMMANDS_DIR", plugin_dir / "commands"),
        patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace),
    ):
        server = create_server()
        result = call(server, "get_docs_map", {"view": "skills"})

    assert "Skill Map" in result["_display"]
    assert map_path.exists()


def test_build_docs_map_empty_dirs(tmp_path, workspace):
    """build_docs_map handles empty skills/ and commands/ dirs gracefully."""
    (tmp_path / "skills").mkdir()
    (tmp_path / "commands").mkdir()

    with (
        patch("extensions.gh_management.github_planner._PLUGIN_DIR", tmp_path),
        patch("extensions.gh_management.github_planner._COMMANDS_DIR", tmp_path / "commands"),
        patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace),
    ):
        server = create_server()
        result = call(server, "build_docs_map", {})

    assert result["skills"] == {}
    assert result["commands"] == {}
    assert "docs_map.json built" in result["_display"]
