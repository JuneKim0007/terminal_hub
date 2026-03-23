"""Tests for server.py internals: get_github_client, get_workspace_root, prompt."""
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from terminal_hub.server import create_server
from extensions.gh_management.github_planner import get_github_client, get_workspace_root


# ── get_workspace_root ────────────────────────────────────────────────────────

def test_get_workspace_root_returns_path():
    result = get_workspace_root()
    assert isinstance(result, Path)
    assert result == Path.cwd()


# ── get_github_client ─────────────────────────────────────────────────────────

def test_get_github_client_no_token_returns_none():
    from extensions.gh_management.github_planner.auth import TokenSource
    with patch("extensions.gh_management.github_planner.resolve_token", return_value=(None, TokenSource.NONE)):
        client, msg = get_github_client()
    assert client is None
    assert "check_auth" in msg


def test_get_github_client_success():
    from extensions.gh_management.github_planner.auth import TokenSource
    with patch("extensions.gh_management.github_planner.resolve_token", return_value=("tok", TokenSource.ENV)), \
         patch("extensions.gh_management.github_planner.detect_repo", return_value="owner/repo"):
        client, msg = get_github_client()
    assert client is not None
    assert msg == ""
    assert client.repo == "owner/repo"


def test_get_github_client_no_repo_returns_error():
    from extensions.gh_management.github_planner.auth import TokenSource
    with patch("extensions.gh_management.github_planner.resolve_token", return_value=("tok", TokenSource.ENV)), \
         patch("extensions.gh_management.github_planner.detect_repo", return_value=None):
        client, msg = get_github_client()
    assert client is None
    assert "setup_workspace" in msg


# ── terminal_hub_instructions prompt ─────────────────────────────────────────

def test_server_instructions_on_demand_message(tmp_path):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
    assert "terminal-hub connected" in server.instructions


# ── draft_issue: local write failure ─────────────────────────────────────────

def test_draft_issue_local_write_failure_returns_error(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.write_issue_file", side_effect=OSError("disk full")):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool(
            "draft_issue", {"title": "x", "body": "y"}
        ))

    assert result["error"] == "draft_failed"
    assert result["_hook"] is None


# ── ensure_initialized guard ──────────────────────────────────────────────────

def test_tools_return_needs_init_when_hub_agents_missing(tmp_path):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool("list_issues", {}))
    assert result["status"] == "needs_init"


# ── auth.py cache hit coverage ─────────────────────────────────────────────────

def test_resolve_token_cache_hit():
    """resolve_token() returns cached value on second call (auth.py:38)."""
    from extensions.gh_management.github_planner.auth import resolve_token, invalidate_token_cache
    invalidate_token_cache()

    with patch("extensions.gh_management.github_planner.auth.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="token123\n", stderr="")
        t1, _ = resolve_token()
        t2, _ = resolve_token()  # cache hit

    assert t1 == t2 == "token123"
    assert mock_run.call_count == 1  # only called once


# ── commands.py error branches ─────────────────────────────────────────────────

def test_commands_load_failure():
    """_load() raises RuntimeError when hub_commands.json is unreadable (17-18)."""
    import extensions.gh_management.github_planner.commands as cmd_mod
    with patch.object(cmd_mod.Path, "read_text", side_effect=OSError("no file")):
        with pytest.raises(RuntimeError, match="Failed to load hub_commands.json"):
            cmd_mod._load()


def test_commands_malformed_entry():
    """endpoint() raises ValueError when stored value has no space separator (39)."""
    from extensions.gh_management.github_planner.commands import endpoint
    import extensions.gh_management.github_planner.commands as cmd_mod
    # Inject a malformed entry (no space = no method/path split)
    cmd_mod._CMDS.setdefault("github", {})["bad_entry"] = "NOSPACE"
    try:
        with pytest.raises(ValueError, match="Malformed command entry"):
            endpoint("github", "bad_entry")
    finally:
        cmd_mod._CMDS["github"].pop("bad_entry", None)


# ── storage.py error branches ──────────────────────────────────────────────────

@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def test_read_doc_file_unknown_key(workspace):
    """read_doc_file raises ValueError for unknown doc_key (224)."""
    from extensions.gh_management.github_planner.storage import read_doc_file
    with pytest.raises(ValueError, match="Unknown doc_key"):
        read_doc_file(workspace, "nonexistent_key")


def test_read_doc_file_oserror(workspace):
    """read_doc_file returns None when file read fails (229-230)."""
    from extensions.gh_management.github_planner.storage import read_doc_file
    # project_description new path is hub_agents/extensions/gh_planner/project_summary.md
    new_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "project_summary.md"
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text("content")
    with patch("extensions.gh_management.github_planner.storage.Path.read_text", side_effect=OSError("perm denied")):
        result = read_doc_file(workspace, "project_description")
    assert result is None


# ── _assert_builtins RuntimeError ─────────────────────────────────────────────

def test_assert_builtins_raises_when_file_missing():
    """_assert_builtins raises RuntimeError when a builtin command file is missing (line 49)."""
    import terminal_hub.server as srv
    original = srv._BUILTIN_COMMANDS
    try:
        srv._BUILTIN_COMMANDS = ["nonexistent_file_abc.md"]
        with pytest.raises(RuntimeError, match="Missing builtin command files"):
            srv._assert_builtins()
    finally:
        srv._BUILTIN_COMMANDS = original


# ── plugin load warning ────────────────────────────────────────────────────────

def test_plugin_load_warning_recorded(tmp_path):
    """A failing plugin load appends to _PLUGIN_WARNINGS (line 404)."""
    import terminal_hub.server as srv
    from terminal_hub.plugin_loader import discover_plugins

    bad_manifest = {
        "name": "bad_plugin",
        "version": "1.0",
        "entry": "extensions.nonexistent_module_xyz",
        "commands_dir": "commands",
        "commands": [],
        "_path": str(tmp_path / "bad_plugin" / "plugin.json"),
        "_plugin_dir": str(tmp_path / "bad_plugin"),
    }

    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path), \
         patch("terminal_hub.server.discover_plugins", return_value=[bad_manifest]):
        server = create_server()

    # After create_server, _PLUGIN_WARNINGS should contain at least one warning
    assert len(srv._PLUGIN_WARNINGS) >= 1


# ── scan_plugins unidentified count ───────────────────────────────────────────

def test_scan_plugins_unidentified_via_read_text_mock(workspace):
    """scan_plugins marks plugins without usage as unidentified (line 325)."""
    import asyncio
    import terminal_hub.server as srv_mod
    from pathlib import Path as RealPath

    project_root = RealPath(__file__).parent.parent
    ext_dir = project_root / "extensions"
    real_paths = sorted(ext_dir.rglob("description.json"))
    if not real_paths:
        pytest.skip("No real description.json found")

    target = real_paths[0]
    orig_read_text = RealPath.read_text

    def patched_read_text(self, *args, **kwargs):
        if self == target:
            return '{"name": "no_usage_plugin"}'  # no usage field
        return orig_read_text(self, *args, **kwargs)

    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()

    with patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch.object(RealPath, "read_text", patched_read_text):
        result = asyncio.run(server._tool_manager.call_tool("scan_plugins", {}))

    assert result.get("unidentified", 0) >= 1
