"""Tests for dispatch_task error paths and _save_config in plugin_customization (#178)."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from terminal_hub.server import create_server


def call(server, tool_name, args=None):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args or {}))


# ── _save_config persistence ───────────────────────────────────────────────────

def test_save_config_writes_and_reloads(tmp_path):
    """_save_config persists to hub_agents/extensions/plugin_customization/plugin_config.json."""
    import extensions.plugin_customization as pc
    with patch("extensions.plugin_customization.resolve_workspace_root", return_value=tmp_path):
        cfg = {"model_routing": {"default": "claude-sonnet-4-6", "tasks": {"my_task": "claude-haiku-4-5-20251001"}}}
        pc._save_config(cfg)

    out = tmp_path / "hub_agents" / "extensions" / "plugin_customization" / "plugin_config.json"
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["model_routing"]["tasks"]["my_task"] == "claude-haiku-4-5-20251001"


def test_save_config_creates_parent_dirs(tmp_path):
    """_save_config creates intermediate directories if they don't exist."""
    import extensions.plugin_customization as pc
    with patch("extensions.plugin_customization.resolve_workspace_root", return_value=tmp_path):
        pc._save_config({"model_routing": {"default": "claude-sonnet-4-6", "tasks": {}}})

    assert (tmp_path / "hub_agents" / "extensions" / "plugin_customization").is_dir()


def test_set_model_for_task_persists_via_save_config(tmp_path):
    """set_model_for_task calls _save_config → file appears on disk."""
    import extensions.plugin_customization as pc
    with patch("extensions.plugin_customization.resolve_workspace_root", return_value=tmp_path):
        result = pc._do_set_model_for_task("file_location", "claude-haiku-4-5-20251001")

    assert result["task_type"] == "file_location"
    out = tmp_path / "hub_agents" / "extensions" / "plugin_customization" / "plugin_config.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["model_routing"]["tasks"]["file_location"] == "claude-haiku-4-5-20251001"


# ── dispatch_task ImportError path ─────────────────────────────────────────────

def test_dispatch_task_missing_anthropic_returns_error():
    """When anthropic is not installed, dispatch_task returns missing_dependency error."""
    import extensions.plugin_customization as pc

    # Temporarily remove anthropic from sys.modules to simulate ImportError
    original = sys.modules.get("anthropic", None)
    sys.modules["anthropic"] = None  # type: ignore[assignment]
    try:
        result = pc._do_dispatch_task("file_location", "find auth files")
    finally:
        if original is None:
            del sys.modules["anthropic"]
        else:
            sys.modules["anthropic"] = original

    assert result["error"] == "missing_dependency"
    assert "anthropic" in result["message"]
    assert "❌" in result["_display"]


def test_dispatch_task_import_error_via_patch():
    """ImportError from lazy import → missing_dependency."""
    import extensions.plugin_customization as pc

    with patch.dict(sys.modules, {"anthropic": None}):
        result = pc._do_dispatch_task("structure_scan", "scan the repo")

    assert result["error"] == "missing_dependency"


# ── dispatch_task API exception path ──────────────────────────────────────────

def test_dispatch_task_api_exception_returns_api_error():
    """Exception from client.messages.create → api_error."""
    import extensions.plugin_customization as pc

    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_client.messages.create.side_effect = RuntimeError("connection refused")

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = pc._do_dispatch_task("file_location", "find auth")

    assert result["error"] == "api_error"
    assert "connection refused" in result["message"]
    assert "❌" in result["_display"]


def test_dispatch_task_api_exception_message_in_display():
    """The exception message appears in _display."""
    import extensions.plugin_customization as pc

    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_client.messages.create.side_effect = ValueError("token expired")

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = pc._do_dispatch_task("issue_classification", "classify this")

    assert "token expired" in result["_display"]


# ── Structured JSON parse and result promotion ─────────────────────────────────

def _mock_anthropic_response(text: str):
    """Build a mock anthropic module that returns `text` from messages.create."""
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = msg
    return mock_anthropic


def test_file_location_promotes_files_key():
    """file_location with valid JSON array → result['files'] promoted."""
    import extensions.plugin_customization as pc
    payload = json.dumps(["/src/auth.py", "/tests/test_auth.py"])

    with patch.dict(sys.modules, {"anthropic": _mock_anthropic_response(payload)}):
        result = pc._do_dispatch_task("file_location", "find auth")

    assert result["files"] == ["/src/auth.py", "/tests/test_auth.py"]
    assert result["result"] == ["/src/auth.py", "/tests/test_auth.py"]


def test_issue_classification_promotes_size_and_reason():
    """issue_classification with valid JSON dict → result['size'] and result['reason'] promoted."""
    import extensions.plugin_customization as pc
    payload = json.dumps({"size": "small", "reason": "single file change"})

    with patch.dict(sys.modules, {"anthropic": _mock_anthropic_response(payload)}):
        result = pc._do_dispatch_task("issue_classification", "classify: add docstring")

    assert result["size"] == "small"
    assert result["reason"] == "single file change"


def test_structure_scan_promotes_areas_key():
    """structure_scan with valid JSON array → result['areas'] promoted."""
    import extensions.plugin_customization as pc
    payload = json.dumps([{"dir": "src/", "purpose": "main source"}, {"dir": "tests/", "purpose": "tests"}])

    with patch.dict(sys.modules, {"anthropic": _mock_anthropic_response(payload)}):
        result = pc._do_dispatch_task("structure_scan", "scan the repo")

    assert len(result["areas"]) == 2
    assert result["areas"][0]["dir"] == "src/"


def test_unknown_task_type_no_promotion():
    """Unknown task type → no promotion keys, raw string result."""
    import extensions.plugin_customization as pc

    with patch.dict(sys.modules, {"anthropic": _mock_anthropic_response("plain response")}):
        result = pc._do_dispatch_task("custom_task", "do something")

    assert result["result"] == "plain response"
    assert "files" not in result
    assert "size" not in result
    assert "areas" not in result


def test_structured_task_invalid_json_returns_raw():
    """Structured task type with non-JSON response → falls back to raw string."""
    import extensions.plugin_customization as pc

    with patch.dict(sys.modules, {"anthropic": _mock_anthropic_response("not json at all")}):
        result = pc._do_dispatch_task("file_location", "find something")

    assert result["result"] == "not json at all"
    assert "files" not in result  # list check fails for string


def test_dispatch_task_uses_model_from_config(tmp_path):
    """dispatch_task picks up model from config for task_type."""
    import extensions.plugin_customization as pc

    captured_model = {}

    def fake_create(**kwargs):
        captured_model["model"] = kwargs["model"]
        msg = MagicMock()
        msg.content = [MagicMock(text="[]")]
        return msg

    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_client.messages.create.side_effect = fake_create

    with patch("extensions.plugin_customization.resolve_workspace_root", return_value=tmp_path), \
         patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        # Set a custom model for file_location
        pc._do_set_model_for_task("file_location", "claude-opus-4-6")
        pc._do_dispatch_task("file_location", "find files")

    assert captured_model["model"] == "claude-opus-4-6"


def test_dispatch_task_display_shows_task_and_model():
    """Success display shows task_type and model."""
    import extensions.plugin_customization as pc

    with patch.dict(sys.modules, {"anthropic": _mock_anthropic_response("result")}):
        result = pc._do_dispatch_task("custom_task", "prompt")

    assert "custom_task" in result["_display"]
    assert result["task_type"] == "custom_task"
    assert "model_used" in result


# ── _do_get_plugin_config ──────────────────────────────────────────────────────

def test_get_plugin_config_returns_config_and_path():
    import extensions.plugin_customization as pc
    result = pc._do_get_plugin_config()
    assert "config" in result
    assert "config_path" in result
    assert "_display" in result
    assert "Model Routing Config" in result["_display"]


def test_get_plugin_config_display_has_default_model():
    import extensions.plugin_customization as pc
    result = pc._do_get_plugin_config()
    assert "claude-sonnet-4-6" in result["_display"] or "claude-haiku" in result["_display"]


def test_get_plugin_config_via_mcp_tool():
    server = create_server()
    result = call(server, "get_plugin_config", {})
    assert "config" in result
    assert "_display" in result


# ── _do_list_task_types ────────────────────────────────────────────────────────

def test_list_task_types_returns_task_list():
    import extensions.plugin_customization as pc
    result = pc._do_list_task_types()
    assert "task_types" in result
    assert "default_model" in result
    assert "_display" in result
    assert "Task → Model routing" in result["_display"]


def test_list_task_types_via_mcp_tool():
    server = create_server()
    result = call(server, "list_task_types", {})
    assert "task_types" in result
    assert "default_model" in result


# ── _do_set_model_for_task unknown model ───────────────────────────────────────

def test_set_model_unknown_returns_error():
    import extensions.plugin_customization as pc
    result = pc._do_set_model_for_task("file_location", "gpt-4o")
    assert result["error"] == "unknown_model"
    assert "gpt-4o" in result["message"]
    assert "❌" in result["_display"]


def test_set_model_for_task_via_mcp_tool(tmp_path):
    with patch("extensions.plugin_customization.resolve_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "set_model_for_task", {
            "task_type": "file_location",
            "model": "claude-haiku-4-5-20251001",
        })
    assert result.get("error") is None
    assert result["task_type"] == "file_location"


def test_dispatch_task_via_mcp_tool_import_error():
    """MCP tool wrapper reaches _do_dispatch_task → missing_dependency when no anthropic."""
    server = create_server()
    with patch.dict(sys.modules, {"anthropic": None}):
        result = call(server, "dispatch_task", {"task_type": "file_location", "prompt": "find auth"})
    assert result["error"] == "missing_dependency"
