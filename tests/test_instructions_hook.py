"""Tests for guided prompt hook: resources, _guidance fields, workflow files."""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from terminal_hub.server import _BUILTIN_DIR, _load_agent, create_server

# ── helpers ───────────────────────────────────────────────────────────────────

def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


def read_resource(server, uri: str) -> str:
    contents = asyncio.run(server.read_resource(uri))
    return contents[0].content


# ── _load_agent ───────────────────────────────────────────────────────────────

def test_load_agent_returns_string_for_existing_file():
    content = _load_agent("help.md")
    assert isinstance(content, str)
    assert len(content) > 0


def test_load_agent_returns_empty_string_for_missing_file():
    assert _load_agent("nonexistent_file.md") == ""


# ── MCP resources registered ──────────────────────────────────────────────────

@pytest.fixture
def server():
    return create_server()


def test_instructions_resource_is_registered(server):
    resources = asyncio.run(server.list_resources())
    uris = [str(r.uri) for r in resources]
    assert "terminal-hub://instructions" in uris


def test_workflow_resources_are_registered(server):
    resources = asyncio.run(server.list_resources())
    uris = [str(r.uri) for r in resources]
    for expected in [
        "terminal-hub://workflow/init",
        "terminal-hub://workflow/issue",
        "terminal-hub://workflow/context",
        "terminal-hub://workflow/auth",
    ]:
        assert expected in uris, f"Missing resource: {expected}"


def test_instructions_resource_returns_entry_point_content(server):
    result = read_resource(server, "terminal-hub://instructions")
    expected = _load_agent("help.md")
    assert result == expected


def test_instructions_resource_content_non_empty(server):
    result = read_resource(server, "terminal-hub://instructions")
    assert len(result) > 0


def test_instructions_matches_file_on_disk(server):
    result = read_resource(server, "terminal-hub://instructions")
    on_disk = (_BUILTIN_DIR / "help.md").read_text()
    assert result == on_disk


# ── workflow files exist on disk ──────────────────────────────────────────────

@pytest.mark.parametrize("filename", ["help.md"])
def test_workflow_file_exists(filename):
    assert (_BUILTIN_DIR / filename).exists(), f"Missing: commands/builtin/{filename}"


_PLUGIN_COMMANDS_DIR = Path(__file__).parent.parent / "plugins" / "github_planner" / "commands"


@pytest.mark.parametrize("filename", [
    "setup.md",
    "create.md",
    "context.md",
    "auth.md",
])
def test_plugin_workflow_file_exists(filename):
    assert (_PLUGIN_COMMANDS_DIR / filename).exists(), f"Missing: plugins/github_planner/commands/{filename}"


def test_workflow_init_resource_has_content(server):
    result = read_resource(server, "terminal-hub://workflow/init")
    assert "setup_workspace" in result


def test_workflow_issue_resource_has_content(server):
    result = read_resource(server, "terminal-hub://workflow/issue")
    assert len(result) > 0  # content loaded from workflow_issue.md


def test_workflow_context_resource_has_content(server):
    result = read_resource(server, "terminal-hub://workflow/context")
    assert "get_project_context" in result


def test_workflow_auth_resource_has_content(server):
    result = read_resource(server, "terminal-hub://workflow/auth")
    assert "check_auth" in result


# ── _guidance field in tool responses ────────────────────────────────────────

def test_needs_init_includes_guidance(tmp_path):
    with patch("plugins.github_planner.get_workspace_root", return_value=tmp_path):
        s = create_server()
        result = call(s, "list_issues", {})
    assert result["status"] == "needs_init"
    assert result["_guidance"] == "terminal-hub://workflow/init"


def test_get_setup_status_uninitialised_includes_guidance(tmp_path):
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        s = create_server()
        result = call(s, "get_setup_status", {})
    assert result["_guidance"] == "terminal-hub://workflow/init"


def test_github_unavailable_includes_guidance(tmp_path):
    import json
    from datetime import date
    from plugins.github_planner.auth import TokenSource
    from plugins.github_planner.storage import write_issue_file
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    write_issue_file(root=tmp_path, slug="x", title="x", body="y",
                     assignees=[], labels=[], created_at=date.today())
    with patch("plugins.github_planner.get_workspace_root", return_value=tmp_path), \
         patch("plugins.github_planner.resolve_token", return_value=(None, TokenSource.NONE)):
        s = create_server()
        result = call(s, "submit_issue", {"slug": "x"})
    assert result["error"] == "github_unavailable"
    assert result["_guidance"] == "terminal-hub://workflow/auth"


def test_check_auth_unauthenticated_includes_guidance(tmp_path):
    from plugins.github_planner.auth import TokenSource
    with patch("plugins.github_planner.get_workspace_root", return_value=tmp_path), \
         patch("plugins.github_planner.resolve_token", return_value=(None, TokenSource.NONE)):
        s = create_server()
        result = call(s, "check_auth", {})
    assert result["authenticated"] is False
    assert result["_guidance"] == "terminal-hub://workflow/auth"


def test_verify_auth_failure_includes_guidance(tmp_path):
    with patch("plugins.github_planner.get_workspace_root", return_value=tmp_path), \
         patch("plugins.github_planner.verify_gh_cli_auth", return_value=(False, "Not logged in")):
        s = create_server()
        result = call(s, "verify_auth", {})
    assert result["authenticated"] is False
    assert result["_guidance"] == "terminal-hub://workflow/auth"


# ── FastMCP instructions injected at init ─────────────────────────────────────

def test_server_instructions_set():
    s = create_server()
    assert s.instructions
    assert "terminal-hub" in s.instructions


# ── .claude/settings.json hook config ────────────────────────────────────────

def test_claude_settings_hook_exists():
    settings = Path(__file__).parent.parent / ".claude" / "settings.json"
    assert settings.exists(), ".claude/settings.json not found"


def test_claude_settings_has_pretooluse_hook():
    settings = Path(__file__).parent.parent / ".claude" / "settings.json"
    data = json.loads(settings.read_text())
    assert "PreToolUse" in data.get("hooks", {})


def test_claude_settings_hook_matches_terminal_hub():
    settings = Path(__file__).parent.parent / ".claude" / "settings.json"
    data = json.loads(settings.read_text())
    hooks = data["hooks"]["PreToolUse"]
    matchers = [h["matcher"] for h in hooks]
    assert any("terminal-hub" in m for m in matchers)
