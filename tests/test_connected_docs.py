"""Tests for connected docs system (#164): docs_config.json, search_project_docs,
connect_docs, load_connected_docs, and load_project_docs integration."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from extensions.gh_management.github_planner import (
    _PROJECT_DOCS_CACHE,
    _SKILL_REGISTRY,
    _do_connect_docs,
    _do_load_connected_docs,
    _do_load_project_docs,
    _do_load_skill,
    _do_search_project_docs,
    _docs_config_path,
    _load_docs_config,
    _load_skill_registry,
)


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear module-level caches before and after each test."""
    _PROJECT_DOCS_CACHE.clear()
    _SKILL_REGISTRY.clear()
    yield
    _PROJECT_DOCS_CACHE.clear()
    _SKILL_REGISTRY.clear()


@pytest.fixture
def workspace(tmp_path):
    """Create a minimal initialised workspace."""
    (tmp_path / "hub_agents" / "extensions" / "gh_planner").mkdir(parents=True)
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def _patch_workspace(workspace):
    return [
        patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace),
        patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None),
        patch("extensions.gh_management.github_planner._resolve_repo", return_value="o/r"),
        patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}),
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

    monkeypatch.setattr("extensions.gh_management.github_planner.get_workspace_root", lambda: tmp_path)

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

    monkeypatch.setattr("extensions.gh_management.github_planner.get_workspace_root", lambda: tmp_path)

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

    monkeypatch.setattr("extensions.gh_management.github_planner.get_workspace_root", lambda: tmp_path)

    result = _do_search_project_docs()
    paths = [c["path"] for c in result["candidates"]]
    assert "REAL.md" in paths
    assert not any("node_modules" in p for p in paths)


# ── test_connect_docs_writes_config ──────────────────────────────────────────

def test_connect_docs_writes_config(workspace):
    """connect_docs() writes docs_config.json with correct structure."""
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text("# Design doc", encoding="utf-8")

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None):
        result = _do_connect_docs(others=["DESIGN.md"])

    assert result.get("connected") is True
    config_path = _docs_config_path(workspace)
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["others"] == ["DESIGN.md"]


def test_connect_docs_clears_when_called_with_none(workspace):
    """connect_docs() with no arguments sets defaults."""
    # First set one
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text("# Design", encoding="utf-8")
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None):
        _do_connect_docs(others=["DESIGN.md"])
        result = _do_connect_docs(primary=None, others=[])

    assert result.get("connected") is True
    config = json.loads(_docs_config_path(workspace).read_text(encoding="utf-8"))
    assert config["others"] == []
    assert config["primary"] == "hub_agents/project_summary.md"


# ── test_connect_docs_missing_other_ref_returns_error ──────────────────────────────────────

def test_connect_docs_missing_other_ref_returns_error(workspace):
    """If a path in others does not exist, return error dict."""
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None):
        result = _do_connect_docs(others=["MISSING_OTHER.md"])

    assert result.get("error") == "ref_not_found"
    assert "MISSING_OTHER.md" in result.get("path", "")


# ── test_load_connected_docs_returns_content ─────────────────────────────────

def test_load_connected_docs_returns_content(workspace):
    """load_connected_docs() returns file content after connect_docs()."""
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text("# Design\n## API\nEndpoints here.", encoding="utf-8")

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None):
        _do_connect_docs(others=["DESIGN.md"])
        result = _do_load_connected_docs()

    assert result.get("content") is not None
    assert "Endpoints here" in result["content"]
    assert "DESIGN.md" in result.get("paths", [])


def test_load_connected_docs_returns_section(workspace):
    """load_connected_docs(section=...) extracts only the requested H2 section."""
    content = "# Design\n## API\nEndpoints here.\n## Storage\nDB schema.\n"
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text(content, encoding="utf-8")

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None):
        _do_connect_docs(others=["DESIGN.md"])
        result = _do_load_connected_docs(section="API")

    assert "Endpoints here" in result["content"]
    # Should not include Storage section
    assert "DB schema" not in result["content"]


def test_load_connected_docs_no_primary_returns_warning(workspace):
    """load_connected_docs() without others connected returns a warning, not an error raise."""
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        result = _do_load_connected_docs()

    assert result.get("content") is None
    assert "connect_docs(others=[...])" in result.get("_display", "")


# ── test_load_project_docs_merges_primary_ref ────────────────────────────────

def test_load_project_docs_merges_primary_ref(workspace):
    """load_project_docs() does NOT merge external docs (primary_reference merge removed)."""
    # Write project_summary.md
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    (docs_dir / "project_summary.md").write_text(
        "# MyProject\nA cool project.", encoding="utf-8"
    )

    # Write a connected primary reference (old style)
    ref_file = workspace / "DESIGN.md"
    ref_file.write_text("# Design\n## Architecture\nThree-tier arch.", encoding="utf-8")

    # Write docs_config.json directly (old format)
    config = {"primary_reference": {"path": "DESIGN.md"}, "other_references": [], "th_generated": True}
    (docs_dir / "docs_config.json").write_text(json.dumps(config), encoding="utf-8")

    patches = _patch_workspace(workspace)
    with patches[0], patches[1], patches[2], patches[3]:
        result = _do_load_project_docs(doc="summary")

    summary = result.get("summary", "")
    assert "A cool project" in summary
    # Primary reference merge is removed — external doc should NOT appear in summary
    assert "Connected Reference" not in summary
    assert "primary ref" not in result.get("_display", "")


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
    assert config["primary"] == "hub_agents/project_summary.md"
    assert config["detail"] == "hub_agents/project_detail.md"
    assert config["skills"] is None
    assert config["others"] == []


# ── test_load_skill ──────────────────────────────────────────────────────────

def test_load_skill_found(tmp_path):
    """load_skill returns content for a skill found in a Tier 1 plugin skills dir."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_file = skills_dir / "my-skill.md"
    skill_file.write_text("---\nname: my-skill\nalwaysApply: false\ntriggers: []\n---\n# My Skill\nDo something.", encoding="utf-8")

    import extensions.gh_management.github_planner as mod
    original_skills_dir = Path(mod.__file__).parent / "skills"

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path), \
         patch.object(Path(mod.__file__).parent.__class__, "__truediv__", side_effect=lambda self, other: tmp_path / "skills" if other == "skills" else Path.__truediv__(self, other)):
        # Manually build registry to avoid patching Path arithmetic
        registry = {
            "my-skill": {
                "path": str(skill_file),
                "alwaysApply": False,
                "triggers": [],
                "tier": "plugin",
            }
        }
        _SKILL_REGISTRY[str(tmp_path)] = registry
        result = _do_load_skill("my-skill")

    assert result.get("error") is None
    assert result["name"] == "my-skill"
    assert "Do something" in result["content"]
    assert result["tier"] == "plugin"


def test_load_skill_not_found(tmp_path):
    """load_skill returns error dict when skill name is not in the registry."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_file = skills_dir / "existing-skill.md"
    skill_file.write_text("---\nname: existing-skill\n---\n# Existing", encoding="utf-8")

    _SKILL_REGISTRY[str(tmp_path)] = {
        "existing-skill": {
            "path": str(skill_file),
            "alwaysApply": False,
            "triggers": [],
            "tier": "plugin",
        }
    }

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_load_skill("nonexistent-skill")

    assert result.get("error") == "skill_not_found"
    assert "existing-skill" in result.get("available", [])


def test_load_skill_tier2_overrides_tier1(tmp_path):
    """Tier 2 project skills override Tier 1 plugin skills on name collision."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    tier1_file = skills_dir / "shared-skill.md"
    tier1_file.write_text("---\nname: shared-skill\n---\n# Tier1 Version", encoding="utf-8")

    project_skills_dir = tmp_path / "my_skills"
    project_skills_dir.mkdir()
    tier2_file = project_skills_dir / "shared-skill.md"
    tier2_file.write_text("---\nname: shared-skill\n---\n# Tier2 Version", encoding="utf-8")

    # Build registry with tier2 override
    registry: dict = {}
    import extensions.gh_management.github_planner as mod
    mod._parse_skills_dir(skills_dir, registry, tier="plugin")
    mod._parse_skills_dir(project_skills_dir, registry, tier="project")
    _SKILL_REGISTRY[str(tmp_path)] = registry

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_load_skill("shared-skill")

    assert result.get("error") is None
    assert result["tier"] == "project"
    assert "Tier2 Version" in result["content"]
