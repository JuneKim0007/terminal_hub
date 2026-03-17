"""Tests for plugin discovery and loading."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from terminal_hub.plugin_loader import validate_manifest, discover_plugins, load_plugin, build_instructions

VALID = {
    "name": "test_plugin", "version": "1.0",
    "entry": "some.module", "commands_dir": "commands",
    "commands": ["start.md"],
}

def test_validate_manifest_valid():
    assert validate_manifest(VALID) == []

def test_validate_manifest_missing_field():
    m = {k: v for k, v in VALID.items() if k != "entry"}
    errors = validate_manifest(m)
    assert any("entry" in e for e in errors)

def test_validate_manifest_missing_multiple_fields():
    m = {"name": "test_plugin"}
    errors = validate_manifest(m)
    assert len(errors) >= 3  # missing version, entry, commands_dir, commands

def test_validate_manifest_invalid_name():
    m = {**VALID, "name": "bad name!"}
    errors = validate_manifest(m)
    assert any("alphanumeric" in e for e in errors)

def test_validate_manifest_name_with_hyphens_underscores():
    m = {**VALID, "name": "my-plugin_v2"}
    assert validate_manifest(m) == []

def test_discover_plugins_empty_dir(tmp_path):
    assert discover_plugins(tmp_path / "plugins") == []

def test_discover_plugins_finds_valid(tmp_path):
    p = tmp_path / "myplugin"
    p.mkdir()
    (p / "plugin.json").write_text(json.dumps(VALID))
    result = discover_plugins(tmp_path)
    assert len(result) == 1
    assert result[0]["name"] == "test_plugin"

def test_discover_plugins_sets_plugin_dir(tmp_path):
    p = tmp_path / "myplugin"
    p.mkdir()
    (p / "plugin.json").write_text(json.dumps(VALID))
    result = discover_plugins(tmp_path)
    assert result[0]["_plugin_dir"] == str(p)

def test_discover_plugins_skips_invalid_json(tmp_path):
    p = tmp_path / "bad"
    p.mkdir()
    (p / "plugin.json").write_text("{not valid json")
    assert discover_plugins(tmp_path) == []

def test_discover_plugins_skips_invalid_manifest(tmp_path):
    p = tmp_path / "bad"
    p.mkdir()
    (p / "plugin.json").write_text(json.dumps({"name": "only_name"}))
    assert discover_plugins(tmp_path) == []

def test_discover_plugins_multiple(tmp_path):
    for name in ["plugin_a", "plugin_b"]:
        p = tmp_path / name
        p.mkdir()
        (p / "plugin.json").write_text(json.dumps({**VALID, "name": name}))
    result = discover_plugins(tmp_path)
    assert len(result) == 2
    names = [r["name"] for r in result]
    assert "plugin_a" in names
    assert "plugin_b" in names

def test_load_plugin_success():
    mock_mod = MagicMock()
    with patch("importlib.import_module", return_value=mock_mod):
        err = load_plugin({**VALID, "_plugin_dir": "."}, MagicMock())
    assert err is None
    mock_mod.register.assert_called_once()

def test_load_plugin_import_error():
    with patch("importlib.import_module", side_effect=ImportError("no module")):
        err = load_plugin({**VALID, "_plugin_dir": "."}, MagicMock())
    assert err is not None
    assert "test_plugin" in err

def test_load_plugin_register_error():
    mock_mod = MagicMock()
    mock_mod.register.side_effect = RuntimeError("register failed")
    with patch("importlib.import_module", return_value=mock_mod):
        err = load_plugin({**VALID, "_plugin_dir": "."}, MagicMock())
    assert err is not None
    assert "test_plugin" in err

def test_build_instructions_includes_plugin_name():
    result = build_instructions([{**VALID, "description": "A test plugin", "conversation_triggers": ["test this"]}])
    assert "test_plugin" in result
    assert "test this" in result

def test_build_instructions_includes_description():
    result = build_instructions([{**VALID, "description": "My plugin description"}])
    assert "My plugin description" in result

def test_build_instructions_no_plugins():
    result = build_instructions([])
    assert "terminal-hub connected" in result

def test_build_instructions_limits_triggers():
    triggers = ["t1", "t2", "t3", "t4", "t5"]
    result = build_instructions([{**VALID, "description": "", "conversation_triggers": triggers}])
    # Should include at most first 3 triggers
    assert '"t1"' in result
    assert '"t4"' not in result

def test_build_instructions_no_triggers():
    result = build_instructions([{**VALID, "description": ""}])
    assert "test_plugin" in result
    assert "Offer to enable" not in result


# ── discover_plugins reads description.json (#55) ─────────────────────────────

def test_discover_plugins_reads_description_json(tmp_path):
    p = tmp_path / "myplugin"
    p.mkdir()
    (p / "plugin.json").write_text(json.dumps(VALID))
    desc = {"plugin": "test_plugin", "subcommands": [{"command": "/t-h:start", "use_when": "start"}]}
    (p / "description.json").write_text(json.dumps(desc))
    result = discover_plugins(tmp_path)
    assert result[0]["_description"]["subcommands"][0]["command"] == "/t-h:start"


def test_discover_plugins_description_json_missing_degrades_gracefully(tmp_path):
    p = tmp_path / "myplugin"
    p.mkdir()
    (p / "plugin.json").write_text(json.dumps(VALID))
    result = discover_plugins(tmp_path)
    assert "_description" not in result[0]


def test_discover_plugins_description_json_invalid_json_degrades_gracefully(tmp_path):
    p = tmp_path / "myplugin"
    p.mkdir()
    (p / "plugin.json").write_text(json.dumps(VALID))
    (p / "description.json").write_text("{bad json")
    result = discover_plugins(tmp_path)
    assert "_description" not in result[0]


# ── build_instructions uses install_namespace + entry_command (#53/#55) ───────

def test_build_instructions_uses_install_namespace():
    manifest = {
        **VALID,
        "description": "A plugin",
        "install_namespace": "t-h",
        "entry_command": "github-planner.md",
    }
    result = build_instructions([manifest])
    assert "/t-h:github-planner" in result


def test_build_instructions_falls_back_to_name_if_no_namespace():
    manifest = {**VALID, "description": "A plugin"}
    result = build_instructions([manifest])
    assert "/test_plugin:" in result


def test_build_instructions_injects_subcommands_from_description_json():
    desc = {
        "subcommands": [
            {"command": "/t-h:github-planner/list-issues", "aliases": ["list issues"], "use_when": "user wants to see open issues"},
            {"command": "/t-h:github-planner/create-issue", "aliases": [], "use_when": "user wants to file a bug"},
        ]
    }
    manifest = {
        **VALID,
        "description": "Planner",
        "install_namespace": "t-h",
        "entry_command": "github-planner.md",
        "_description": desc,
    }
    result = build_instructions([manifest])
    assert "list-issues" in result
    assert "user wants to see open issues" in result
    assert "create-issue" in result


def test_build_instructions_limits_subcommands_to_six():
    subcommands = [
        {"command": f"/t-h:cmd{i}", "aliases": [], "use_when": f"when {i}"}
        for i in range(10)
    ]
    manifest = {**VALID, "description": "", "_description": {"subcommands": subcommands}}
    result = build_instructions([manifest])
    assert "/t-h:cmd5" in result   # 6th (index 5) included
    assert "/t-h:cmd6" not in result  # 7th excluded
