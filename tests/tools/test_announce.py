"""Tests for announce_command_load — the first call of every /th: command.

It shipped with no coverage at all despite being documented as mandatory.
"""
import asyncio
import json
from unittest.mock import patch

import pytest

from terminal_hub.server import create_server


def call(server, args):
    return asyncio.run(server._tool_manager.call_tool("announce_command_load", args))


@pytest.fixture
def announce(tmp_path):
    """Call the tool with ~/.claude/commands/th pointed at a temp dir."""
    commands_root = tmp_path / ".claude" / "commands" / "th"
    commands_root.mkdir(parents=True)

    def run(command, prompt_exists=True, extensions=None):
        if prompt_exists:
            (commands_root / f"{command}.md").write_text("# prompt", encoding="utf-8")
        server = create_server()
        # After create_server: it repopulates _LOADED_EXTENSIONS, so an
        # injected value must be set once the server exists.
        import terminal_hub.server as srv
        saved = list(srv._LOADED_EXTENSIONS)
        if extensions is not None:
            srv._LOADED_EXTENSIONS[:] = extensions
        try:
            with patch("terminal_hub.server.tools.announce.Path.home", return_value=tmp_path):
                return call(server, {"command": command})
        finally:
            srv._LOADED_EXTENSIONS[:] = saved

    return run


def test_reports_the_loaded_prompt_and_tool_count(announce):
    result = announce("gh-plan")

    assert result["command"] == "gh-plan"
    assert result["prompt_exists"] is True
    assert result["prompt_path"].endswith("commands/th/gh-plan.md")
    assert result["registered_tools"] > 0
    assert "🟢 /th:gh-plan — prompt loaded" in result["_display"]


def test_warns_when_the_prompt_file_is_missing(announce):
    """A /th: command whose prompt was never installed must say so, not fail."""
    result = announce("never-installed", prompt_exists=False)

    assert result["prompt_exists"] is False
    assert "⚠ prompt file not found" in result["_display"]


def test_lists_loaded_extensions_with_their_summary(announce, tmp_path):
    """Each extension is listed with the summary from its description.json."""
    manifest = tmp_path / "demo" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    (manifest.parent / "description.json").write_text(
        json.dumps({"summary": "does a demo thing"}), encoding="utf-8"
    )
    result = announce(
        "gh-plan",
        extensions=[{"name": "demo", "tools": ["a", "b"], "manifest_path": str(manifest)}],
    )

    assert result["loaded_extensions"][0]["name"] == "demo"
    assert "• demo — does a demo thing (2 tools)" in result["_display"]
