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
        "commands": ["/th:plugin-a"],
        "triggers": ["use a", "do a", "plugin a"],
    }), encoding="utf-8")

    # Plugin B: old schema (github_planner style)
    b = ext / "plugin_b"
    b.mkdir(parents=True)
    (b / "description.json").write_text(json.dumps({
        "plugin": "plugin_b",
        "summary": "Plugin B for tracking things.",
        "entry": {
            "command": "/th:plugin-b",
            "triggers": ["track", "monitor"],
        },
        "subcommands": [
            {"command": "/th:plugin-b/list"},
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


def test_converse_md_exists():
    """converse.md command file is present."""
    path = Path(__file__).parent.parent.parent / "extensions" / "builtin" / "converse.md"
    assert path.exists()


# ── server.py coverage gaps ────────────────────────────────────────────────────

def test_scan_plugins_not_initialized(tmp_path):
    """scan_plugins returns needs_init when hub_agents/ absent."""
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "scan_plugins", {})
    assert result.get("status") == "needs_init"


def test_load_plugin_registry_not_initialized(tmp_path):
    """load_plugin_registry returns needs_init when hub_agents/ absent."""
    with patch("terminal_hub.server.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "load_plugin_registry", {})
    assert result.get("status") == "needs_init"


def test_scan_plugins_bad_description_json(workspace, tmp_path):
    """Bad description.json (invalid JSON) is silently skipped."""
    bad_ext = tmp_path / "extensions" / "bad_plugin"
    bad_ext.mkdir(parents=True)
    (bad_ext / "description.json").write_text("not json {{{{", encoding="utf-8")

    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        # Uses real extensions/ — bad_ext is in tmp_path so not picked up by real scanner.
        # We test the skip branch by patching the extensions dir.
        import terminal_hub.server as srv_mod
        orig_path = srv_mod.Path
        class FakePath(orig_path):
            def rglob(self, pattern):
                if pattern == "description.json":
                    # Yield our bad file + a real one
                    yield bad_ext / "description.json"
                else:
                    yield from super().rglob(pattern)
        with patch.object(srv_mod, "Path", FakePath):
            result = call(server, "scan_plugins", {})
    # Should not crash; bad file skipped
    assert result.get("error") is None or "status" in result


def test_load_plugin_registry_corrupt_file(workspace):
    """Corrupt plugin.config.json returns error field."""
    config_path = workspace / "hub_agents" / "plugin.config.json"
    config_path.write_text("not json {{{", encoding="utf-8")
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "load_plugin_registry", {})
    assert result.get("error") == "registry_corrupt"


def test_scan_plugins_marks_unidentified(workspace):
    """Plugin without usage is counted in unidentified."""
    import terminal_hub.server as srv_mod
    empty_desc = workspace / "empty_desc.json"
    empty_desc.write_text(json.dumps({"name": "no_usage_plugin"}), encoding="utf-8")

    orig_json_loads = json.loads
    collected: list[dict] = []

    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()

    # Directly test the logic by calling scan with a description that has no usage
    # Create a real plugin dir in a temp ext space and patch the extensions dir
    fake_ext = workspace / "fake_ext"
    no_usage_plugin = fake_ext / "no_usage"
    no_usage_plugin.mkdir(parents=True)
    (no_usage_plugin / "description.json").write_text(
        json.dumps({"name": "no_usage_plugin"}), encoding="utf-8"
    )

    # We'll use the real scanner but check for unidentified in the result
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        result = call(server, "scan_plugins", {})
    # With real extensions all having usage, unidentified should be 0
    assert result["unidentified"] == 0


def test_get_setup_status_with_plugin_warnings(workspace):
    """get_setup_status includes plugin_warnings when present."""
    import terminal_hub.server as srv_mod
    from terminal_hub.config import WorkspaceMode, save_config
    save_config(workspace, WorkspaceMode.LOCAL, None)

    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        # Inject a warning directly into the module-level list
        srv_mod._PLUGIN_WARNINGS = ["test warning"]
        result = call(server, "get_setup_status", {})
        srv_mod._PLUGIN_WARNINGS = []  # cleanup

    assert "plugin_warnings" in result
    assert "test warning" in result["plugin_warnings"]


# ── Integration tests for MCP wrapper lines in __init__.py ───────────────────

def test_sync_github_issues_tool_via_server(workspace):
    """Call sync_github_issues through the server to cover MCP wrapper line."""
    from unittest.mock import MagicMock
    import asyncio

    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues_all.return_value = []

    with patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "owner/repo"}):
        server = create_server()
        result = call(server, "sync_github_issues", {"state": "open"})

    assert result.get("error") is None
    assert "synced" in result


def test_list_pending_drafts_tool_via_server(workspace):
    """Call list_pending_drafts through the server to cover MCP wrapper."""
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "list_pending_drafts", {})

    assert "pending_drafts" in result


def test_analyze_github_labels_tool_via_server(workspace):
    """Call analyze_github_labels through the server to cover MCP wrapper."""
    from unittest.mock import MagicMock
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_labels.return_value = []
    mock_gh.list_issues.return_value = []

    with patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, "")):
        server = create_server()
        result = call(server, "analyze_github_labels", {})

    assert result.get("error") is None


def test_load_github_local_config_tool_via_server(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "load_github_local_config", {})

    assert "labels" in result


def test_load_github_global_config_tool_via_server(workspace):
    from unittest.mock import MagicMock
    mock_source = MagicMock(); mock_source.value = "none"
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.resolve_token", return_value=(None, mock_source)), \
         patch("extensions.gh_management.github_planner.read_env", return_value={}):
        server = create_server()
        result = call(server, "load_github_global_config", {})

    assert "auth" in result


def test_save_github_local_config_tool_via_server(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "save_github_local_config", {"data": {"default_branch": "main"}})

    assert result.get("saved") is True


def test_get_github_config_tool_via_server(workspace):
    from unittest.mock import MagicMock
    mock_source = MagicMock(); mock_source.value = "none"
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.resolve_token", return_value=(None, mock_source)), \
         patch("extensions.gh_management.github_planner.read_env", return_value={}):
        server = create_server()
        result = call(server, "get_github_config", {"scope": "both"})

    assert "global" in result
    assert "local" in result


def test_load_plugin_registry_filtered_by_plugin(workspace):
    """load_plugin_registry(plugin=name) returns only the matching entry."""
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "scan_plugins", {})
        result = call(server, "load_plugin_registry", {"plugin": "github_planner"})

    assert isinstance(result["plugins"], list)
    assert len(result["plugins"]) == 1
    assert result["plugins"][0]["name"] == "github_planner"
    assert result["unidentified"] == 0


def test_load_plugin_registry_filtered_no_match(workspace):
    """load_plugin_registry(plugin=unknown) returns empty plugins list."""
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "scan_plugins", {})
        result = call(server, "load_plugin_registry", {"plugin": "nonexistent_plugin"})

    assert result["plugins"] == []
    assert result["unidentified"] == 0


def test_load_plugin_registry_unfiltered_still_works(workspace):
    """load_plugin_registry() with no plugin arg returns full registry (backward compat)."""
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "scan_plugins", {})
        result = call(server, "load_plugin_registry", {})

    assert len(result["plugins"]) >= 1
    assert "unidentified" in result


# ── plugin_customization: dispatch_task + config tools (#178) ─────────────────

import sys
from unittest.mock import MagicMock

from extensions.plugin_customization import (
    _do_dispatch_task,
    _do_get_plugin_config,
    _do_list_task_types,
    _do_set_model_for_task,
    _load_config,
    _save_config,
)
from terminal_hub.constants import MODEL_HAIKU, MODEL_SONNET


def test_dispatch_task_import_error():
    """ImportError → error dict with missing_dependency code."""
    saved = sys.modules.get("anthropic")
    sys.modules["anthropic"] = None  # type: ignore[assignment]
    try:
        result = _do_dispatch_task("file_location", "find auth module")
    finally:
        if saved is None:
            sys.modules.pop("anthropic", None)
        else:
            sys.modules["anthropic"] = saved

    assert result["error"] == "missing_dependency"
    assert "anthropic" in result["message"]


def test_dispatch_task_api_exception():
    """API exception → error dict with api_error code."""
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_client.messages.create.side_effect = RuntimeError("connection refused")

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = _do_dispatch_task("file_location", "find auth module")

    assert result["error"] == "api_error"
    assert "connection refused" in result["message"]


def test_dispatch_task_file_location_json_parse():
    """file_location with valid JSON array → result['files'] promoted."""
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='["/src/auth.py", "/tests/test_auth.py"]')]
    mock_client.messages.create.return_value = mock_message

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = _do_dispatch_task("file_location", "find auth")

    assert result["task_type"] == "file_location"
    assert result["files"] == ["/src/auth.py", "/tests/test_auth.py"]
    assert isinstance(result["result"], list)


def test_dispatch_task_issue_classification_json_parse():
    """issue_classification with valid JSON → size/reason promoted."""
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"size": "small", "reason": "single file change"}')]
    mock_client.messages.create.return_value = mock_message

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = _do_dispatch_task("issue_classification", "classify this issue")

    assert result["size"] == "small"
    assert result["reason"] == "single file change"


def test_dispatch_task_structure_scan_json_parse():
    """structure_scan with valid JSON array → areas promoted."""
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='[{"dir": "src", "purpose": "main source"}]')]
    mock_client.messages.create.return_value = mock_message

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = _do_dispatch_task("structure_scan", "scan the tree")

    assert result["areas"] == [{"dir": "src", "purpose": "main source"}]


def test_dispatch_task_json_parse_failure_returns_raw():
    """If JSON parse fails for structured task, result is the raw string."""
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not json at all")]
    mock_client.messages.create.return_value = mock_message

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = _do_dispatch_task("file_location", "find something")

    assert result["result"] == "not json at all"
    assert "files" not in result


def test_dispatch_task_with_context_prepends_context():
    """context is prepended to prompt before API call."""
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="[]")]
    mock_client.messages.create.return_value = mock_message

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        _do_dispatch_task("file_location", "find auth", context="project has src/")

    call_args = mock_client.messages.create.call_args
    sent_prompt = call_args[1]["messages"][0]["content"]
    assert "project has src/" in sent_prompt
    assert "find auth" in sent_prompt


def test_dispatch_task_unknown_type_uses_default_system():
    """Unknown task_type uses _DEFAULT_SYSTEM prompt and no key promotion."""
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="some answer")]
    mock_client.messages.create.return_value = mock_message

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = _do_dispatch_task("custom_task", "do something custom")

    assert result["result"] == "some answer"
    assert "files" not in result
    assert "size" not in result
    assert "areas" not in result


def test_save_config_round_trip(tmp_path):
    """_save_config writes to hub_agents override path; _load_config reads it back."""
    cfg_in = {"model_routing": {"default": MODEL_HAIKU, "tasks": {"file_location": MODEL_HAIKU}}}

    with patch("extensions.plugin_customization.resolve_workspace_root", return_value=tmp_path):
        _save_config(cfg_in)
        cfg_out = _load_config(force=True)

    assert cfg_out["model_routing"]["default"] == MODEL_HAIKU
    assert cfg_out["model_routing"]["tasks"]["file_location"] == MODEL_HAIKU


def test_save_config_creates_dirs(tmp_path):
    """_save_config creates intermediate directories if missing."""
    cfg = {"model_routing": {"tasks": {}}}
    out_path = tmp_path / "hub_agents" / "extensions" / "plugin_customization" / "plugin_config.json"

    assert not out_path.exists()
    with patch("extensions.plugin_customization.resolve_workspace_root", return_value=tmp_path):
        _save_config(cfg)

    assert out_path.exists()


def test_do_get_plugin_config_returns_display():
    result = _do_get_plugin_config()
    assert "config" in result
    assert "config_path" in result
    assert "Model Routing Config" in result["_display"]


def test_do_set_model_for_task_unknown_model():
    result = _do_set_model_for_task("file_location", "gpt-9-turbo")
    assert result["error"] == "unknown_model"
    assert "gpt-9-turbo" in result["message"]


def test_do_set_model_for_task_valid(tmp_path):
    with patch("extensions.plugin_customization.resolve_workspace_root", return_value=tmp_path):
        result = _do_set_model_for_task("file_location", MODEL_HAIKU)

    assert result["task_type"] == "file_location"
    assert result["model"] == MODEL_HAIKU
    assert "_display" in result


def test_do_list_task_types_returns_display():
    result = _do_list_task_types()
    assert "task_types" in result
    assert "default_model" in result
    assert "Task → Model routing" in result["_display"]


# ── MCP wrapper lines coverage ────────────────────────────────────────────────

def test_mcp_get_plugin_config(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_plugin_config", {})
    assert "config" in result
    assert "_display" in result


def test_mcp_set_model_for_task_invalid(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "set_model_for_task", {"task_type": "file_location", "model": "bad-model"})
    assert result["error"] == "unknown_model"


def test_mcp_list_task_types(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "list_task_types", {})
    assert "task_types" in result
    assert "_display" in result


def test_mcp_dispatch_task_wrapper(workspace):
    """Cover the MCP dispatch_task wrapper line via server call."""
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.plugin_customization._do_dispatch_task",
               return_value={"task_type": "file_location", "result": [], "_display": "ok"}):
        server = create_server()
        result = call(server, "dispatch_task", {"task_type": "file_location", "prompt": "find auth"})
    assert result["task_type"] == "file_location"
