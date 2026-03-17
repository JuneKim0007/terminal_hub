"""Tests for the centralized error message loader."""
import json
from pathlib import Path
import pytest
from terminal_hub.errors import msg, _MSGS


def test_msg_returns_string_for_known_key():
    result = msg("auth_failed")
    assert isinstance(result, str)
    assert len(result) > 0


def test_msg_formats_kwargs():
    result = msg("validation_failed", detail="bad label")
    assert "bad label" in result


def test_msg_unknown_key_returns_fallback():
    result = msg("totally_unknown_key_xyz")
    assert "totally_unknown_key_xyz" in result


def test_all_keys_in_json_are_non_empty():
    for key, value in _MSGS.items():
        assert isinstance(value, str) and len(value) > 0, f"empty message for key: {key}"


def test_required_keys_exist():
    required = [
        "auth_failed", "permission_denied", "repo_not_found", "validation_failed",
        "rate_limited", "network_error", "timeout", "github_error",
        "draft_failed", "submit_failed", "label_bootstrap_failed",
        "not_found", "write_failed", "invalid_json", "missing_field",
    ]
    for key in required:
        assert key in _MSGS, f"missing key in error_msg.json: {key}"


def test_error_msg_json_is_valid():
    path = Path(__file__).parent.parent / "terminal_hub" / "error_msg.json"
    data = json.loads(path.read_text())
    assert isinstance(data, dict)


def test_load_raises_runtime_error_on_missing_file(monkeypatch):
    from unittest.mock import patch
    from terminal_hub import errors
    with patch("terminal_hub.errors.Path.read_text", side_effect=OSError("no file")):
        with pytest.raises(RuntimeError, match="Failed to load error_msg.json"):
            errors._load()


def test_msg_missing_placeholder_returns_error_string():
    from terminal_hub import errors
    original = errors._MSGS.copy()
    errors._MSGS["_test_key"] = "Hello {name} and {missing}"
    try:
        result = errors.msg("_test_key", name="world")
        assert "missing placeholder" in result
        assert "_test_key" in result
    finally:
        errors._MSGS.pop("_test_key", None)
