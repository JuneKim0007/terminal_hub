"""Tests for the centralized command/endpoint loader."""
import json
from pathlib import Path
import pytest
from terminal_hub.commands import endpoint, _CMDS


def test_endpoint_returns_method_and_path():
    method, path = endpoint("github", "create_issue")
    assert method == "POST"
    assert "/issues" in path


def test_endpoint_list_labels():
    method, path = endpoint("github", "list_labels")
    assert method == "GET"
    assert "labels" in path


def test_endpoint_create_label():
    method, path = endpoint("github", "create_label")
    assert method == "POST"
    assert "labels" in path


def test_gh_cli_commands_defined():
    assert "auth_token" in _CMDS["gh_cli"]
    assert "auth_status" in _CMDS["gh_cli"]


def test_endpoint_path_is_formattable():
    _, path = endpoint("github", "create_issue")
    url = "https://api.github.com" + path.format(repo="owner/repo")
    assert "owner/repo" in url


def test_hub_commands_json_is_valid():
    path = Path(__file__).parent.parent / "terminal_hub" / "hub_commands.json"
    data = json.loads(path.read_text())
    assert "github" in data
    assert "gh_cli" in data


def test_all_github_commands_have_method_and_path():
    for name, value in _CMDS["github"].items():
        parts = value.split(" ", 1)
        assert len(parts) == 2, f"command '{name}' missing method or path"
        assert parts[0].isupper(), f"command '{name}' method not uppercase"


def test_unknown_command_raises_key_error():
    with pytest.raises(KeyError):
        endpoint("github", "nonexistent_command")


def test_load_raises_runtime_error_on_missing_file(monkeypatch):
    from unittest.mock import patch
    from terminal_hub import commands
    with patch("terminal_hub.commands.Path.read_text", side_effect=OSError("no file")):
        with pytest.raises(RuntimeError, match="Failed to load hub_commands.json"):
            commands._load()


def test_endpoint_raises_value_error_for_malformed_entry():
    from terminal_hub import commands
    original = commands._CMDS.copy()
    commands._CMDS.setdefault("github", {})["_bad"] = "NOSPACEINHERE"
    try:
        with pytest.raises(ValueError, match="Malformed command entry"):
            endpoint("github", "_bad")
    finally:
        commands._CMDS["github"].pop("_bad", None)
