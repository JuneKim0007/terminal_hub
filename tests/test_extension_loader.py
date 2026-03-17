"""Tests for terminal_hub.extension_loader."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from terminal_hub.extension_loader import (
    check_deps,
    load_config,
    load_extensions,
    validate_extension,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_config(tmp_path: Path, data: object) -> Path:
    p = tmp_path / "command_config.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _valid_ext(**kwargs) -> dict:
    base = {
        "id": "myext",
        "description": "A test extension",
        "invoke": "/terminal_hub:myext",
        "requires": [],
        "fallback": "claude",
        "platforms": {"darwin": ["echo hi"], "linux": ["echo hi"]},
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_missing_file_returns_empty_list(self, tmp_path: Path):
        result = load_config(tmp_path / "nonexistent.json")
        assert result == []

    def test_invalid_json_raises_runtime_error(self, tmp_path: Path):
        p = tmp_path / "command_config.json"
        p.write_text("not valid json{{{", encoding="utf-8")
        with pytest.raises(RuntimeError, match="Failed to load"):
            load_config(p)

    def test_missing_extensions_key_raises_runtime_error(self, tmp_path: Path):
        p = _write_config(tmp_path, {"version": 1})
        with pytest.raises(RuntimeError, match="missing 'extensions' key"):
            load_config(p)

    def test_valid_file_returns_extensions_list(self, tmp_path: Path):
        exts = [_valid_ext()]
        p = _write_config(tmp_path, {"version": 1, "extensions": exts})
        result = load_config(p)
        assert result == exts

    def test_empty_extensions_list(self, tmp_path: Path):
        p = _write_config(tmp_path, {"version": 1, "extensions": []})
        assert load_config(p) == []

    def test_non_dict_root_raises_runtime_error(self, tmp_path: Path):
        p = _write_config(tmp_path, [1, 2, 3])
        with pytest.raises(RuntimeError, match="missing 'extensions' key"):
            load_config(p)


# ---------------------------------------------------------------------------
# check_deps
# ---------------------------------------------------------------------------

class TestCheckDeps:
    def test_all_tools_found_returns_true_empty_list(self):
        ext = _valid_ext(requires=["python"])
        with patch("shutil.which", return_value="/usr/bin/python"):
            ok, missing = check_deps(ext)
        assert ok is True
        assert missing == []

    def test_missing_tool_returns_false_with_list(self):
        ext = _valid_ext(requires=["nonexistent_tool_xyz"])
        with patch("shutil.which", return_value=None):
            ok, missing = check_deps(ext)
        assert ok is False
        assert "nonexistent_tool_xyz" in missing

    def test_no_requires_returns_true(self):
        ext = _valid_ext(requires=[])
        ok, missing = check_deps(ext)
        assert ok is True
        assert missing == []

    def test_partial_missing(self):
        ext = _valid_ext(requires=["git", "missing_cmd"])

        def fake_which(cmd):
            return "/usr/bin/git" if cmd == "git" else None

        with patch("shutil.which", side_effect=fake_which):
            ok, missing = check_deps(ext)
        assert ok is False
        assert missing == ["missing_cmd"]


# ---------------------------------------------------------------------------
# validate_extension
# ---------------------------------------------------------------------------

class TestValidateExtension:
    def test_valid_extension_returns_no_errors(self):
        assert validate_extension(_valid_ext()) == []

    def test_missing_id_returns_error(self):
        ext = _valid_ext()
        del ext["id"]
        errors = validate_extension(ext)
        assert any("missing 'id'" in e for e in errors)

    def test_empty_id_returns_error(self):
        errors = validate_extension(_valid_ext(id=""))
        assert any("missing 'id'" in e for e in errors)

    def test_missing_platforms_returns_error(self):
        ext = _valid_ext()
        del ext["platforms"]
        errors = validate_extension(ext)
        assert any("missing 'platforms'" in e for e in errors)

    def test_empty_platforms_returns_error(self):
        errors = validate_extension(_valid_ext(platforms={}))
        assert any("missing 'platforms'" in e for e in errors)

    def test_invalid_fallback_returns_error(self):
        errors = validate_extension(_valid_ext(fallback="explode"))
        assert any("invalid fallback" in e for e in errors)

    def test_valid_fallbacks_accepted(self):
        for fb in (None, "claude", "skip", "abort"):
            ext = _valid_ext()
            if fb is None:
                ext.pop("fallback", None)
            else:
                ext["fallback"] = fb
            assert validate_extension(ext) == [], f"fallback={fb!r} should be valid"

    def test_multiple_errors_returned(self):
        ext = {"fallback": "bad"}
        errors = validate_extension(ext)
        # missing id, missing platforms, invalid fallback
        assert len(errors) >= 3


# ---------------------------------------------------------------------------
# load_extensions
# ---------------------------------------------------------------------------

class TestLoadExtensions:
    def test_skips_comment_entries_with_underscore_id(self, tmp_path: Path):
        comment_ext = {"id": "_comment", "platforms": {"darwin": ["echo hi"]}}
        real_ext = _valid_ext()
        ext_dir = tmp_path / "extensions"
        ext_dir.mkdir()
        _write_config(ext_dir, {"version": 1, "extensions": [comment_ext, real_ext]})
        with patch("shutil.which", return_value="/usr/bin/something"):
            result = load_extensions(tmp_path)
        assert all(e["id"] != "_comment" for e in result)
        assert any(e["id"] == "myext" for e in result)

    def test_skips_entries_with_comment_key(self, tmp_path: Path):
        comment_ext = {"_comment": "Example", "id": "example", "platforms": {"darwin": []}}
        real_ext = _valid_ext()
        ext_dir = tmp_path / "extensions"
        ext_dir.mkdir()
        _write_config(ext_dir, {"version": 1, "extensions": [comment_ext, real_ext]})
        with patch("shutil.which", return_value="/usr/bin/something"):
            result = load_extensions(tmp_path)
        assert all("_comment" not in e for e in result)

    def test_skips_invalid_extensions_with_warning(self, tmp_path: Path, capsys):
        invalid_ext = {"description": "no id or platforms"}
        ext_dir = tmp_path / "extensions"
        ext_dir.mkdir()
        _write_config(ext_dir, {"version": 1, "extensions": [invalid_ext]})
        with patch("shutil.which", return_value="/usr/bin/something"):
            result = load_extensions(tmp_path)
        assert result == []
        captured = capsys.readouterr()
        assert "skipped" in captured.out

    def test_skips_extensions_with_missing_deps(self, tmp_path: Path, capsys):
        ext = _valid_ext(requires=["totally_missing_tool"])
        ext_dir = tmp_path / "extensions"
        ext_dir.mkdir()
        _write_config(ext_dir, {"version": 1, "extensions": [ext]})
        with patch("shutil.which", return_value=None):
            result = load_extensions(tmp_path)
        assert result == []
        captured = capsys.readouterr()
        assert "disabled" in captured.out

    def test_returns_only_enabled_extensions(self, tmp_path: Path):
        good = _valid_ext(id="good", requires=["present_tool"])
        bad = _valid_ext(id="bad", requires=["absent_tool"])
        ext_dir = tmp_path / "extensions"
        ext_dir.mkdir()
        _write_config(ext_dir, {"version": 1, "extensions": [good, bad]})

        def fake_which(cmd):
            return "/bin/present_tool" if cmd == "present_tool" else None

        with patch("shutil.which", side_effect=fake_which):
            result = load_extensions(tmp_path)

        ids = [e["id"] for e in result]
        assert "good" in ids
        assert "bad" not in ids

    def test_no_config_returns_empty_list(self, tmp_path: Path):
        result = load_extensions(tmp_path)
        assert result == []

    def test_warns_on_invalid_config_file(self, tmp_path: Path, capsys):
        ext_dir = tmp_path / "extensions"
        ext_dir.mkdir()
        (ext_dir / "command_config.json").write_text("{{bad json", encoding="utf-8")
        result = load_extensions(tmp_path)
        assert result == []
        captured = capsys.readouterr()
        assert "⚠" in captured.out

    def test_searches_hub_agents_config(self, tmp_path: Path):
        hub_ext_dir = tmp_path / "hub_agents" / "extensions"
        hub_ext_dir.mkdir(parents=True)
        ext = _valid_ext(id="hub_ext")
        _write_config(hub_ext_dir, {"version": 1, "extensions": [ext]})
        with patch("shutil.which", return_value="/usr/bin/something"):
            result = load_extensions(tmp_path)
        assert any(e["id"] == "hub_ext" for e in result)
