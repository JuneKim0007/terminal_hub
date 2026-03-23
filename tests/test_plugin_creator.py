"""Tests for plugin_creator plugin: write_plugin_file, write_test_file, validate_plugin."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from extensions.plugin_creator import (
    _do_validate_plugin,
    _do_write_plugin_file,
    _do_write_test_file,
    register,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_valid_plugin(plugins_dir: Path, name: str = "myplugin") -> Path:
    """Write a minimal valid plugin to plugins_dir/<name>/."""
    plugin_dir = plugins_dir / name
    (plugin_dir / "commands").mkdir(parents=True)

    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": name,
        "version": "1.0",
        "entry": f"extensions.{name}",
        "commands_dir": "commands",
        "commands": ["start.md"],
    }))
    (plugin_dir / "__init__.py").write_text(
        f'"""Plugin."""\n\ndef register(mcp) -> None:\n    pass\n'
    )
    (plugin_dir / "description.json").write_text(json.dumps({"plugin": name}))
    (plugin_dir / "commands" / "start.md").write_text("# start")
    return plugin_dir


# ── register ──────────────────────────────────────────────────────────────────

def test_register_is_callable():
    assert callable(register)


def test_register_does_not_raise():
    register(MagicMock())


# ── write_plugin_file ─────────────────────────────────────────────────────────

def test_write_plugin_file_creates_file(tmp_path):
    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
        result = _do_write_plugin_file("myplugin", "plugin.json", '{"name": "myplugin"}')
    assert result["written"] is True
    assert (tmp_path / "myplugin" / "plugin.json").read_text() == '{"name": "myplugin"}'


def test_write_plugin_file_creates_subdirectory(tmp_path):
    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
        result = _do_write_plugin_file("myplugin", "commands/start.md", "# start")
    assert result["written"] is True
    assert (tmp_path / "myplugin" / "commands" / "start.md").exists()


def test_write_plugin_file_invalid_name_returns_error(tmp_path):
    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
        result = _do_write_plugin_file("bad name!", "file.txt", "x")
    assert result["error"] == "invalid_name"


def test_write_plugin_file_path_traversal_blocked(tmp_path):
    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
        result = _do_write_plugin_file("myplugin", "../../evil.py", "x")
    assert result["error"] == "path_traversal"


# ── write_test_file ───────────────────────────────────────────────────────────

def test_write_test_file_creates_file(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    with patch("extensions.plugin_creator._TESTS_ROOT", tests_dir):
        result = _do_write_test_file("myplugin", "# test content")
    assert result["written"] is True
    assert (tests_dir / "test_myplugin.py").read_text() == "# test content"


def test_write_test_file_normalises_hyphens(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    with patch("extensions.plugin_creator._TESTS_ROOT", tests_dir):
        result = _do_write_test_file("my-plugin", "# test")
    assert result["written"] is True
    assert (tests_dir / "test_my_plugin.py").exists()


def test_write_test_file_invalid_name_returns_error(tmp_path):
    with patch("extensions.plugin_creator._TESTS_ROOT", tmp_path):
        result = _do_write_test_file("bad name!", "x")
    assert result["error"] == "invalid_name"


# ── validate_plugin ───────────────────────────────────────────────────────────

def test_validate_plugin_missing_dir_returns_error(tmp_path):
    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
        result = _do_validate_plugin("nonexistent")
    assert result["valid"] is False
    assert any("does not exist" in e for e in result["errors"])


def test_validate_plugin_missing_manifest_returns_error(tmp_path):
    (tmp_path / "myplugin").mkdir()
    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
        result = _do_validate_plugin("myplugin")
    assert result["valid"] is False
    assert any("plugin.json" in e for e in result["errors"])


def test_validate_plugin_invalid_json_manifest(tmp_path):
    (tmp_path / "myplugin").mkdir()
    (tmp_path / "myplugin" / "plugin.json").write_text("{bad json")
    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
        result = _do_validate_plugin("myplugin")
    assert result["valid"] is False
    assert any("invalid JSON" in e for e in result["errors"])


def test_validate_plugin_missing_register_attribute(tmp_path):
    plugin_dir = tmp_path / "myplugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": "myplugin", "version": "1.0",
        "entry": "extensions.myplugin",
        "commands_dir": "commands", "commands": [],
    }))
    (plugin_dir / "description.json").write_text("{}")

    # Module imports fine but has no register attribute
    mock_mod = MagicMock(spec=[])  # spec=[] means no attributes

    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path), \
         patch("importlib.import_module", return_value=mock_mod):
        result = _do_validate_plugin("myplugin")
    assert result["valid"] is False
    assert any("register" in e for e in result["errors"])


def test_validate_plugin_missing_description_json(tmp_path):
    plugin_dir = tmp_path / "myplugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": "myplugin", "version": "1.0",
        "entry": "extensions.myplugin",
        "commands_dir": "commands", "commands": [],
    }))
    mock_mod = MagicMock()
    mock_mod.register = MagicMock()

    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path), \
         patch("importlib.import_module", return_value=mock_mod):
        result = _do_validate_plugin("myplugin")
    assert result["valid"] is False
    assert any("description.json" in e for e in result["errors"])


def test_validate_plugin_missing_command_file(tmp_path):
    plugin_dir = tmp_path / "myplugin"
    (plugin_dir / "commands").mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": "myplugin", "version": "1.0",
        "entry": "extensions.myplugin",
        "commands_dir": "commands", "commands": ["start.md"],
    }))
    (plugin_dir / "description.json").write_text("{}")
    # start.md intentionally not created
    mock_mod = MagicMock()
    mock_mod.register = MagicMock()

    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path), \
         patch("importlib.import_module", return_value=mock_mod):
        result = _do_validate_plugin("myplugin")
    assert result["valid"] is False
    assert any("start.md" in e for e in result["errors"])


def test_validate_plugin_fully_valid(tmp_path):
    _make_valid_plugin(tmp_path, "myplugin")

    mock_mod = MagicMock()
    mock_mod.register = MagicMock()

    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path), \
         patch("importlib.import_module", return_value=mock_mod):
        result = _do_validate_plugin("myplugin")

    assert result["valid"] is True
    assert result["errors"] == []


# ── MCP tool registration ─────────────────────────────────────────────────────

def test_plugin_creator_tools_registered():
    from terminal_hub.server import create_server
    import asyncio
    from unittest.mock import patch as p2

    server = create_server()
    tool_names = {t.name for t in server._tool_manager.list_tools()}
    assert "write_plugin_file" in tool_names
    assert "write_test_file" in tool_names
    assert "validate_plugin" in tool_names


# ── register() MCP wrapper lines ──────────────────────────────────────────────

def test_register_mcp_write_plugin_file(tmp_path):
    """Calling write_plugin_file via MCP covers register() wrapper line 156."""
    import asyncio
    from terminal_hub.server import create_server
    ext_root = tmp_path / "extensions"
    ext_root.mkdir()
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path), \
         patch("extensions.plugin_creator._EXTENSIONS_ROOT", ext_root), \
         patch("extensions.plugin_creator._TESTS_ROOT", tmp_path / "tests"):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool(
            "write_plugin_file",
            {"plugin_name": "test_plug", "filename": "cmd.md", "content": "# cmd"}
        ))
    assert result.get("written") is True


def test_register_mcp_write_test_file(tmp_path):
    """Calling write_test_file via MCP covers register() wrapper line 165."""
    import asyncio
    from terminal_hub.server import create_server
    tests_root = tmp_path / "tests"
    tests_root.mkdir()
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path), \
         patch("extensions.plugin_creator._TESTS_ROOT", tests_root):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool(
            "write_test_file",
            {"plugin_name": "test_plug", "content": "def test_foo(): pass\n"}
        ))
    assert result.get("written") is True


def test_register_mcp_validate_plugin(tmp_path):
    """Calling validate_plugin via MCP covers register() wrapper line 177."""
    import asyncio
    from terminal_hub.server import create_server
    ext_root = tmp_path / "extensions"
    ext_root.mkdir()
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path), \
         patch("extensions.plugin_creator._EXTENSIONS_ROOT", ext_root):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool(
            "validate_plugin",
            {"plugin_name": "nonexistent_plugin"}
        ))
    # Should return valid=False with errors, not crash
    assert "valid" in result


def test_validate_plugin_register_not_callable(tmp_path):
    """'register' attribute exists but is not callable (line 126)."""
    plugin_dir = tmp_path / "bad_plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": "bad_plugin", "version": "1.0",
        "entry": "extensions.bad_plugin",
        "commands_dir": "commands", "commands": [],
    }))
    (plugin_dir / "description.json").write_text(json.dumps({"plugin": "bad_plugin"}))

    mock_mod = MagicMock()
    mock_mod.register = "not_callable_string"

    with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path), \
         patch("importlib.import_module", return_value=mock_mod):
        result = _do_validate_plugin("bad_plugin")
    assert result["valid"] is False
    assert any("not callable" in e for e in result["errors"])
