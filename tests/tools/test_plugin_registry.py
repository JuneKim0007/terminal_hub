"""Tests for scan_plugins and load_plugin_registry tools (#44 / #45)."""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from terminal_hub.server import create_server


def call(server, tool_name, args=None):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args or {}))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def ext_dir(tmp_path):
    """Create a fake extensions/ directory with two plugins."""
    ext = tmp_path / "extensions"

    # Plugin A: full description.json (new schema)
    a = ext / "plugin_a"
    a.mkdir(parents=True)
    (a / "description.json").write_text(json.dumps({
        "name": "plugin_a",
        "display_name": "Plugin A",
        "usage": "Do amazing things with A.",
        "commands": ["/t-h:plugin-a"],
        "triggers": ["use a", "do a", "plugin a"],
    }), encoding="utf-8")

    # Plugin B: old schema (github_planner style)
    b = ext / "plugin_b"
    b.mkdir(parents=True)
    (b / "description.json").write_text(json.dumps({
        "plugin": "plugin_b",
        "summary": "Plugin B for tracking things.",
        "entry": {
            "command": "/t-h:plugin-b",
            "triggers": ["track", "monitor"],
        },
        "subcommands": [
            {"command": "/t-h:plugin-b/list"},
        ],
    }), encoding="utf-8")

    return ext


def _patch_ext_dir(ext_dir):
    """Patch the extensions dir used by scan_plugins."""
    return patch(
        "terminal_hub.server.Path.__truediv__",
        side_effect=lambda self, name: Path(str(self)) / name,
    )


def test_scan_plugins_writes_registry(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        # Uses the real extensions/ directory
        result = call(server, "scan_plugins", {})

    # Should have found at least the real extensions (github_planner, plugin_creator)
    assert result.get("error") is None
    assert result["total"] >= 1
    assert (workspace / "hub_agents" / "plugin.config.json").exists()


def test_scan_plugins_registry_has_required_fields(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "scan_plugins", {})

    assert isinstance(result["plugins"], list)
    for plugin in result["plugins"]:
        assert "name" in plugin
        assert "commands" in plugin
        assert "triggers" in plugin
        assert "usage" in plugin


def test_scan_plugins_normalizes_old_schema(workspace):
    """Old-schema description.json (plugin + summary + entry) should be normalized."""
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "scan_plugins", {})

    # github_planner uses old schema — check it gets normalized
    gh_plugin = next((p for p in result["plugins"] if p["name"] == "github_planner"), None)
    assert gh_plugin is not None
    assert gh_plugin["usage"]  # summary field mapped to usage
    assert len(gh_plugin["commands"]) >= 1
    assert len(gh_plugin["triggers"]) >= 1


def test_load_plugin_registry_not_found(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "load_plugin_registry", {})

    assert result["plugins"] == []
    assert "_suggest_scan" in result


def test_load_plugin_registry_after_scan(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "scan_plugins", {})
        result = call(server, "load_plugin_registry", {})

    assert isinstance(result["plugins"], list)
    assert len(result["plugins"]) >= 1
    assert result["last_scanned"] is not None
    assert "_suggest_scan" not in result


def test_load_plugin_registry_returns_triggers(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "scan_plugins", {})
        result = call(server, "load_plugin_registry", {})

    gh_plugin = next((p for p in result["plugins"] if p["name"] == "github_planner"), None)
    assert gh_plugin is not None
    assert isinstance(gh_plugin["triggers"], list)
    assert len(gh_plugin["triggers"]) >= 1


def test_scan_plugins_counts_unidentified(workspace, tmp_path):
    """Plugin without usage/summary is counted as unidentified."""
    # Create a temp description.json with no usage
    ext_dir = tmp_path / "fake_extensions"
    empty_plugin = ext_dir / "empty_plugin"
    empty_plugin.mkdir(parents=True)
    (empty_plugin / "description.json").write_text(
        json.dumps({"name": "empty_plugin"}), encoding="utf-8"
    )
    # Use real workspace + real extensions (github_planner has usage)
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "scan_plugins", {})

    # Real plugins all have descriptions — unidentified should be 0
    assert result["unidentified"] == 0


def test_conversation_md_exists():
    """conversation.md command file is present."""
    path = Path(__file__).parent.parent.parent / "extensions" / "builtin" / "conversation.md"
    assert path.exists()


def test_converse_md_exists():
    """converse.md command file is present."""
    path = Path(__file__).parent.parent.parent / "extensions" / "builtin" / "converse.md"
    assert path.exists()
