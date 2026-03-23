"""Tests for format_prompt MCP tool and _do_format_prompt (#177)."""
import asyncio

from terminal_hub.server import create_server
from extensions.prompt_coloring import _do_format_prompt


def call(server, tool_name, args=None):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args or {}))


# ── _do_format_prompt unit tests ──────────────────────────────────────────────

def test_question_style_default():
    result = _do_format_prompt("Ready?")
    assert result["_display"] == "❓ **Ready?**"
    assert result["style"] == "question"
    assert result["question"] == "Ready?"
    assert result["options"] == []


def test_confirm_style():
    result = _do_format_prompt("All good?", style="confirm")
    assert result["_display"].startswith("✅")
    assert "**All good?**" in result["_display"]


def test_warning_style():
    result = _do_format_prompt("Watch out!", style="warning")
    assert result["_display"].startswith("⚠️")
    assert "**Watch out!**" in result["_display"]


def test_switch_style():
    result = _do_format_prompt("Switching mode", style="switch")
    assert result["_display"].startswith("→")
    assert "**Switching mode**" in result["_display"]


def test_error_style():
    result = _do_format_prompt("Something failed", style="error")
    assert result["_display"].startswith("❌")
    assert "**Something failed**" in result["_display"]


def test_unknown_style_falls_back_to_question():
    result = _do_format_prompt("Hello?", style="nonexistent")
    assert result["_display"].startswith("❓")


def test_options_rendered_as_slash_list():
    result = _do_format_prompt("Choose one", options=["yes", "no", "cancel"])
    assert "*(yes / no / cancel)*" in result["_display"]
    assert result["options"] == ["yes", "no", "cancel"]


def test_single_option():
    result = _do_format_prompt("Confirm?", options=["ok"])
    assert "*(ok)*" in result["_display"]


def test_no_options_no_parens():
    result = _do_format_prompt("Simple question")
    assert "(" not in result["_display"]
    assert result["options"] == []


def test_options_with_non_default_style():
    result = _do_format_prompt("Accept?", options=["yes", "no"], style="confirm")
    assert "✅" in result["_display"]
    assert "*(yes / no)*" in result["_display"]


def test_returns_all_keys():
    result = _do_format_prompt("Q?", options=["a"], style="warning")
    assert set(result.keys()) == {"_display", "style", "question", "options"}


# ── format_prompt MCP tool integration ────────────────────────────────────────

def test_mcp_tool_question_style():
    server = create_server()
    result = call(server, "format_prompt", {"question": "Are you sure?", "style": "question"})
    assert "❓" in result["_display"]
    assert "**Are you sure?**" in result["_display"]


def test_mcp_tool_with_options():
    server = create_server()
    result = call(server, "format_prompt", {
        "question": "Pick one",
        "options": ["a", "b"],
        "style": "confirm",
    })
    assert "✅" in result["_display"]
    assert "*(a / b)*" in result["_display"]


def test_mcp_tool_no_options_key():
    server = create_server()
    result = call(server, "format_prompt", {"question": "Hello?"})
    assert "_display" in result
    assert "Hello?" in result["_display"]


def test_mcp_tool_error_style():
    server = create_server()
    result = call(server, "format_prompt", {"question": "Failed!", "style": "error"})
    assert "❌" in result["_display"]
