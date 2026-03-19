"""Tests for extensions/plugin_customization."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_config(tasks: dict | None = None, default: str = "claude-sonnet-4-6") -> dict:
    return {"model_routing": {"default": default, "tasks": tasks or {}}}


# ── Config loading ────────────────────────────────────────────────────────────

class TestConfigLoading:
    def test_model_for_known_task(self, tmp_path, monkeypatch):
        from extensions.plugin_customization import _do_get_plugin_config, _load_config, _model_for_task

        cfg = _make_config({"file_location": "claude-haiku-4-5-20251001"})
        config_file = tmp_path / "plugin_config.json"
        config_file.write_text(json.dumps(cfg))

        monkeypatch.setattr(
            "extensions.plugin_customization._user_config_path",
            lambda: config_file,
        )
        import extensions.plugin_customization as ext
        ext._config_cache = {}
        ext._config_mtime = 0.0

        assert _model_for_task("file_location") == "claude-haiku-4-5-20251001"

    def test_unknown_task_falls_back_to_default(self, tmp_path, monkeypatch):
        from extensions.plugin_customization import _model_for_task

        cfg = _make_config(default="claude-sonnet-4-6")
        config_file = tmp_path / "plugin_config.json"
        config_file.write_text(json.dumps(cfg))

        monkeypatch.setattr(
            "extensions.plugin_customization._user_config_path",
            lambda: config_file,
        )
        import extensions.plugin_customization as ext
        ext._config_cache = {}
        ext._config_mtime = 0.0

        assert _model_for_task("unknown_task") == "claude-sonnet-4-6"


# ── dispatch_task ─────────────────────────────────────────────────────────────

class TestDispatchTask:
    def _make_anthropic_mock(self, response_text: str):
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=response_text)]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        return mock_anthropic

    def test_file_location_returns_files_key(self, tmp_path, monkeypatch):
        from extensions.plugin_customization import _do_dispatch_task

        cfg = _make_config({"file_location": "claude-haiku-4-5-20251001"})
        config_file = tmp_path / "plugin_config.json"
        config_file.write_text(json.dumps(cfg))
        monkeypatch.setattr("extensions.plugin_customization._user_config_path", lambda: config_file)
        import extensions.plugin_customization as ext
        ext._config_cache = {}; ext._config_mtime = 0.0

        mock_anthropic = self._make_anthropic_mock('["src/auth.py", "tests/test_auth.py"]')
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = _do_dispatch_task("file_location", "find auth files")

        assert result["task_type"] == "file_location"
        assert result["model_used"] == "claude-haiku-4-5-20251001"
        assert result["files"] == ["src/auth.py", "tests/test_auth.py"]

    def test_issue_classification_returns_size_key(self, tmp_path, monkeypatch):
        from extensions.plugin_customization import _do_dispatch_task

        cfg = _make_config({"issue_classification": "claude-haiku-4-5-20251001"})
        config_file = tmp_path / "plugin_config.json"
        config_file.write_text(json.dumps(cfg))
        monkeypatch.setattr("extensions.plugin_customization._user_config_path", lambda: config_file)
        import extensions.plugin_customization as ext
        ext._config_cache = {}; ext._config_mtime = 0.0

        mock_anthropic = self._make_anthropic_mock('{"size": "small", "reason": "single bug fix"}')
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = _do_dispatch_task("issue_classification", "Fix null pointer in auth")

        assert result["size"] == "small"
        assert result["reason"] == "single bug fix"

    def test_structure_scan_returns_areas_key(self, tmp_path, monkeypatch):
        from extensions.plugin_customization import _do_dispatch_task

        cfg = _make_config({"structure_scan": "claude-haiku-4-5-20251001"})
        config_file = tmp_path / "plugin_config.json"
        config_file.write_text(json.dumps(cfg))
        monkeypatch.setattr("extensions.plugin_customization._user_config_path", lambda: config_file)
        import extensions.plugin_customization as ext
        ext._config_cache = {}; ext._config_mtime = 0.0

        mock_anthropic = self._make_anthropic_mock('[{"dir": "src/", "purpose": "main source"}]')
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = _do_dispatch_task("structure_scan", "files:\nsrc/\ntests/")

        assert result["areas"] == [{"dir": "src/", "purpose": "main source"}]

    def test_missing_anthropic_returns_error(self, monkeypatch):
        from extensions.plugin_customization import _do_dispatch_task

        with patch.dict("sys.modules", {"anthropic": None}):
            result = _do_dispatch_task("file_location", "find something")

        assert result["error"] == "missing_dependency"


# ── set_model_for_task ────────────────────────────────────────────────────────

class TestSetModelForTask:
    def test_valid_model_persists(self, tmp_path, monkeypatch):
        from extensions.plugin_customization import _do_set_model_for_task

        cfg = _make_config()
        config_file = tmp_path / "plugin_config.json"
        config_file.write_text(json.dumps(cfg))
        monkeypatch.setattr("extensions.plugin_customization._user_config_path", lambda: config_file)

        override_path = tmp_path / "hub_agents" / "extensions" / "plugin_customization" / "plugin_config.json"
        monkeypatch.setattr(
            "extensions.plugin_customization._save_config",
            lambda c: (override_path.parent.mkdir(parents=True, exist_ok=True), override_path.write_text(json.dumps(c))),
        )
        import extensions.plugin_customization as ext
        ext._config_cache = {}; ext._config_mtime = 0.0

        result = _do_set_model_for_task("file_location", "claude-sonnet-4-6")
        assert result["model"] == "claude-sonnet-4-6"
        assert "error" not in result

    def test_invalid_model_rejected(self):
        from extensions.plugin_customization import _do_set_model_for_task

        result = _do_set_model_for_task("file_location", "gpt-4o")
        assert result["error"] == "unknown_model"


# ── list_task_types ───────────────────────────────────────────────────────────

class TestListTaskTypes:
    def test_returns_all_configured_tasks(self, tmp_path, monkeypatch):
        from extensions.plugin_customization import _do_list_task_types

        cfg = _make_config({"file_location": "claude-haiku-4-5-20251001", "planning": "claude-sonnet-4-6"})
        config_file = tmp_path / "plugin_config.json"
        config_file.write_text(json.dumps(cfg))
        monkeypatch.setattr("extensions.plugin_customization._user_config_path", lambda: config_file)
        import extensions.plugin_customization as ext
        ext._config_cache = {}; ext._config_mtime = 0.0

        result = _do_list_task_types()
        assert "file_location" in result["task_types"]
        assert "planning" in result["task_types"]
        assert "⚡ fast" in result["_display"]
