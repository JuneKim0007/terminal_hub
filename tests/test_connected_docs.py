"""Tests for connected docs system (#164): docs_config.json, search_project_docs,
connect_docs, load_connected_docs, and load_project_docs integration."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from extensions.github_planner import (
    _PROJECT_DOCS_CACHE,
    _do_connect_docs,
    _do_load_connected_docs,
    _do_load_project_docs,
    _do_search_project_docs,
    _docs_config_path,
    _load_docs_config,
)


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear module-level caches before and after each test."""
    _PROJECT_DOCS_CACHE.clear()
    yield
    _PROJECT_DOCS_CACHE.clear()


@pytest.fixture
def workspace(tmp_path):
    """Create a minimal initialised workspace."""
    (tmp_path / "hub_agents" / "extensions" / "gh_planner").mkdir(parents=True)
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def _patch_workspace(workspace):
    return [
        patch("extensions.github_planner.get_workspace_root", return_value=workspace),
        patch("extensions.github_planner.ensure_initialized", return_value=None),
        patch("extensions.github_planner._resolve_repo", return_value="o/r"),
        patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}),
    ]


# ── test_search_excludes_noise ────────────────────────────────────────────────

def test_search_excludes_noise(tmp_path, monkeypatch):
    """CHANGELOG.md and LICENSE.md should be excluded; DESIGN.md should be included."""
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n## v1.0\nSome changes.", encoding="utf-8")
    (tmp_path / "LICENSE.md").write_text("MIT License", encoding="utf-8")
    (tmp_path / "DESIGN.md").write_text("# Design\n## Overview\nThis is the design.", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ARCHITECTURE.md").write_text(
        "# Architecture\n## Layers\nLayer info here.", encoding="utf-8"
    )

    monkeypatch.setattr("extensions.github_planner.get_workspace_root", lambda: tmp_path)

    result = _do_search_project_docs()
    paths = [c["path"] for c in result["candidates"]]

    assert "DESIGN.md" in paths, "DESIGN.md should be a candidate"
    assert "docs/ARCHITECTURE.md" in paths or str(Path("docs") / "ARCHITECTURE.md") in paths
    assert "CHANGELOG.md" not in paths, "CHANGELOG.md should be excluded"
    assert "LICENSE.md" not in paths, "LICENSE.md should be excluded"


def test_search_excludes_noise_case_insensitive(tmp_path, monkeypatch):
    """changelog.md (lower-case) should also be excluded."""
    (tmp_path / "changelog.md").write_text("# changelog\n## v1", encoding="utf-8")
    (tmp_path / "SPEC.md").write_text("# Spec\n## API", encoding="utf-8")

    monkeypatch.setattr("extensions.github_planner.get_workspace_root", lambda: tmp_path)

    result = _do_search_project_docs()
    paths = [c["path"] for c in result["candidates"]]
    assert "changelog.md" not in paths
    assert "SPEC.md" in paths


def test_search_skips_noise_dirs(tmp_path, monkeypatch):
    """Files under node_modules / .git should not appear."""
    node_mods = tmp_path / "node_modules"
    node_mods.mkdir()
    (node_mods / "README.md").write_text("# pkg\n## install", encoding="utf-8")
    (tmp_path / "REAL.md").write_text("# Real doc\n## Section", encoding="utf-8")

    monkeypatch.setattr("extensions.github_planner.get_workspace_root", lambda: tmp_path)

    result = _do_search_project_docs()
    paths = [c["path"] for c in result["candidates"]]
    assert "REAL.md" in paths
    assert not any("node_modules" in p for p in paths)


# ── test_connect_docs_writes_config ──────────────────────────────────────────

def test_connect_docs_writes_config(workspace):
    """connect_docs() writes docs_config.json with correct structure."""
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text("# Design doc", encoding="utf-8")

    primary = {"path": "DESIGN.md", "description": "Main design notes"}

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.ensure_initialized", return_value=None):
        result = _do_connect_docs(primary=primary, others=[])

    assert result.get("connected") is True
    config_path = _docs_config_path(workspace)
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["primary_reference"]["path"] == "DESIGN.md"
    assert config["other_references"] == []


def test_connect_docs_clears_when_called_with_none(workspace):
    """connect_docs() with no arguments clears the primary reference."""
    # First set one
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text("# Design", encoding="utf-8")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.ensure_initialized", return_value=None):
        _do_connect_docs(primary={"path": "DESIGN.md"}, others=[])
        result = _do_connect_docs(primary=None, others=[])

    assert result.get("connected") is True
    config = json.loads(_docs_config_path(workspace).read_text(encoding="utf-8"))
    assert config["primary_reference"] is None


# ── test_connect_docs_missing_primary_returns_error ──────────────────────────

def test_connect_docs_missing_primary_returns_error(workspace):
    """If primary path does not exist, return error dict (not raise)."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.ensure_initialized", return_value=None):
        result = _do_connect_docs(primary={"path": "NONEXISTENT.md"}, others=[])

    assert result.get("error") == "primary_not_found"
    assert "NONEXISTENT.md" in result.get("path", "")


def test_connect_docs_missing_other_ref_returns_error(workspace):
    """If an other_references path does not exist, return error dict."""
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text("# Design", encoding="utf-8")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.ensure_initialized", return_value=None):
        result = _do_connect_docs(
            primary={"path": "DESIGN.md"},
            others=[{"path": "MISSING_OTHER.md"}],
        )

    assert result.get("error") == "ref_not_found"


# ── test_load_connected_docs_returns_content ─────────────────────────────────

def test_load_connected_docs_returns_content(workspace):
    """load_connected_docs() returns file content after connect_docs()."""
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text("# Design\n## API\nEndpoints here.", encoding="utf-8")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.ensure_initialized", return_value=None):
        _do_connect_docs(primary={"path": "DESIGN.md"}, others=[])
        result = _do_load_connected_docs()

    assert result.get("content") is not None
    assert "Endpoints here" in result["content"]
    assert result["path"] == "DESIGN.md"


def test_load_connected_docs_returns_section(workspace):
    """load_connected_docs(section=...) extracts only the requested H2 section."""
    content = "# Design\n## API\nEndpoints here.\n## Storage\nDB schema.\n"
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text(content, encoding="utf-8")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.ensure_initialized", return_value=None):
        _do_connect_docs(primary={"path": "DESIGN.md"}, others=[])
        result = _do_load_connected_docs(section="API")

    assert "Endpoints here" in result["content"]
    # Should not include Storage section
    assert "DB schema" not in result["content"]


def test_load_connected_docs_no_primary_returns_warning(workspace):
    """load_connected_docs() without a primary connected returns a warning, not an error raise."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_load_connected_docs()

    assert result.get("content") is None
    assert "connect_docs" in result.get("_display", "")


# ── test_load_project_docs_merges_primary_ref ────────────────────────────────

def test_load_project_docs_merges_primary_ref(workspace):
    """load_project_docs() merges primary_reference content into summary."""
    # Write project_summary.md
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    (docs_dir / "project_summary.md").write_text(
        "# MyProject\nA cool project.", encoding="utf-8"
    )

    # Write a connected primary reference
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text("# Design\n## Architecture\nThree-tier arch.", encoding="utf-8")

    # Write docs_config.json directly
    config = {"primary_reference": {"path": "DESIGN.md"}, "other_references": [], "th_generated": True}
    (docs_dir / "docs_config.json").write_text(json.dumps(config), encoding="utf-8")

    patches = _patch_workspace(workspace)
    with patches[0], patches[1], patches[2], patches[3]:
        result = _do_load_project_docs(doc="summary")

    summary = result.get("summary", "")
    assert "A cool project" in summary
    assert "Three-tier arch" in summary
    assert "Connected Reference: DESIGN.md" in summary
    assert "primary ref" in result.get("_display", "")


def test_load_project_docs_no_primary_ref_unchanged(workspace):
    """load_project_docs() without a primary reference returns unmodified summary."""
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    (docs_dir / "project_summary.md").write_text("# MyProject\nA cool project.", encoding="utf-8")

    patches = _patch_workspace(workspace)
    with patches[0], patches[1], patches[2], patches[3]:
        result = _do_load_project_docs(doc="summary")

    summary = result.get("summary", "")
    assert "A cool project" in summary
    assert "Connected Reference" not in summary
    assert "primary ref" not in result.get("_display", "")


def test_load_docs_config_defaults_when_missing(workspace):
    """_load_docs_config returns sensible defaults when no file exists."""
    config = _load_docs_config(workspace)
    assert config["primary_reference"] is None
    assert config["other_references"] == []
    assert config.get("th_generated") is True
