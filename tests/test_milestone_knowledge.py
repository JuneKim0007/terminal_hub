"""Tests for milestone knowledge base (#50) and bidirectional sync (#51)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from extensions.gh_management.github_planner import (
    _MILESTONE_CACHE,
    _PROJECT_DOCS_CACHE,
    _do_generate_milestone_knowledge,
    _do_load_milestone_knowledge,
    _load_milestone_index,
    _milestone_knowledge_path,
    _milestones_dir,
)


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear module-level caches before and after each test."""
    _MILESTONE_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    yield
    _MILESTONE_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def _setup_workspace_patches(workspace: Path, milestones=None, summary_text="", detail_text=""):
    """Return a context manager stack with standard workspace patches."""
    import contextlib

    if milestones is None:
        milestones = [{"number": 1, "title": "Core Infrastructure", "description": "Baseline MCP tooling.", "open_issues": 0}]

    repo = "o/r"
    _MILESTONE_CACHE[repo] = milestones

    resolved = repo
    _PROJECT_DOCS_CACHE[resolved] = {
        "summary": summary_text,
        "detail": detail_text,
        "loaded_at": 0.0,
    }

    patches = [
        patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace),
        patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None),
        patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": repo}),
        patch("extensions.gh_management.github_planner._resolve_repo", return_value=repo),
    ]
    return contextlib.ExitStack(), patches


# ── Issue #50 tests ────────────────────────────────────────────────────────────

def test_generate_creates_file_and_index(workspace):
    """generate_milestone_knowledge creates M1.md and updates milestone_index.json."""
    repo = "o/r"
    _MILESTONE_CACHE[repo] = [
        {"number": 1, "title": "Core Infrastructure", "description": "Baseline MCP tooling.", "open_issues": 0}
    ]
    _PROJECT_DOCS_CACHE[repo] = {"summary": "", "detail": "", "loaded_at": 0.0}

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": repo}), \
         patch("extensions.gh_management.github_planner._resolve_repo", return_value=repo):

        result = _do_generate_milestone_knowledge(1)

    assert "error" not in result
    assert result["milestone_number"] == 1
    assert "_display" in result
    assert "M1" in result["_display"]

    # File should exist
    m1_path = _milestone_knowledge_path(workspace, 1)
    assert m1_path.exists(), "M1.md was not created"
    content = m1_path.read_text(encoding="utf-8")
    assert "# M1" in content
    assert "Core Infrastructure" in content
    assert "## Goal" in content
    assert "## Depends On" in content
    assert "## Enables" in content

    # Index should be updated
    index = _load_milestone_index(workspace)
    assert "1" in index
    assert index["1"]["title"] == "Core Infrastructure"
    assert index["1"]["path"] == "milestones/M1.md"
    assert "generated_at" in index["1"]


def test_load_returns_content_when_exists(workspace):
    """load_milestone_knowledge returns content when file exists."""
    # Pre-write a knowledge file
    m_dir = _milestones_dir(workspace)
    m_dir.mkdir(parents=True, exist_ok=True)
    path = _milestone_knowledge_path(workspace, 2)
    path.write_text("# M2 — Agent Routing\n\n## Goal\nTest goal.\n", encoding="utf-8")

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None):

        result = _do_load_milestone_knowledge(2)

    assert result["exists"] is True
    assert result["milestone_number"] == 2
    assert "# M2" in result["content"]
    assert "📄" in result["_display"]


def test_load_returns_not_found_when_missing(workspace):
    """load_milestone_knowledge returns exists=False when file is absent."""
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None):

        result = _do_load_milestone_knowledge(99)

    assert result["exists"] is False
    assert result["milestone_number"] == 99
    assert "generate_milestone_knowledge" in result["_display"] or "not yet generated" in result["_display"]


# ── Issue #51 tests ────────────────────────────────────────────────────────────

def test_generate_updates_enables_in_prior_milestone(workspace):
    """Generating M2 updates M1's Enables section to reference M2."""
    repo = "o/r"

    # Pre-create M1 with Enables: None
    m_dir = _milestones_dir(workspace)
    m_dir.mkdir(parents=True, exist_ok=True)
    m1_path = _milestone_knowledge_path(workspace, 1)
    m1_content = (
        "# M1 — Core Infrastructure\n\n"
        "## Goal\nBaseline tooling.\n\n"
        "## Enables\nNone (last milestone)\n"
    )
    m1_path.write_text(m1_content, encoding="utf-8")

    # Write M1 into index so the linking code finds it
    index_path = workspace / "hub_agents" / "milestones" / "milestone_index.json"
    index_path.write_text(json.dumps({
        "1": {"title": "Core Infrastructure", "path": "milestones/M1.md", "generated_at": "2026-01-01T00:00:00Z"}
    }), encoding="utf-8")

    _MILESTONE_CACHE[repo] = [
        {"number": 2, "title": "Agent Routing", "description": "Route tasks to cheap models.", "open_issues": 0}
    ]
    _PROJECT_DOCS_CACHE[repo] = {"summary": "", "detail": "", "loaded_at": 0.0}

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": repo}), \
         patch("extensions.gh_management.github_planner._resolve_repo", return_value=repo):

        result = _do_generate_milestone_knowledge(2)

    assert "error" not in result

    # M1's Enables section should now mention M2
    updated_m1 = m1_path.read_text(encoding="utf-8")
    assert "M2" in updated_m1, f"Expected M2 in M1 Enables section, got:\n{updated_m1}"


def test_generate_sets_depends_on_from_prior(workspace):
    """Generating M2 when M1 exists sets M2's Depends On to M1."""
    repo = "o/r"

    # M1 is already in the index
    m_dir = _milestones_dir(workspace)
    m_dir.mkdir(parents=True, exist_ok=True)
    m1_path = _milestone_knowledge_path(workspace, 1)
    m1_path.write_text("# M1 — Core Infrastructure\n\n## Enables\nNone (last milestone)\n", encoding="utf-8")

    index_path = workspace / "hub_agents" / "milestones" / "milestone_index.json"
    index_path.write_text(json.dumps({
        "1": {"title": "Core Infrastructure", "path": "milestones/M1.md", "generated_at": "2026-01-01T00:00:00Z"}
    }), encoding="utf-8")

    _MILESTONE_CACHE[repo] = [
        {"number": 2, "title": "Agent Routing", "description": "Route tasks to cheap models.", "open_issues": 0}
    ]
    _PROJECT_DOCS_CACHE[repo] = {"summary": "", "detail": "", "loaded_at": 0.0}

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": repo}), \
         patch("extensions.gh_management.github_planner._resolve_repo", return_value=repo):

        result = _do_generate_milestone_knowledge(2)

    assert "error" not in result

    # M2's knowledge file should have Depends On referencing M1
    m2_path = _milestone_knowledge_path(workspace, 2)
    assert m2_path.exists()
    m2_content = m2_path.read_text(encoding="utf-8")
    assert "## Depends On" in m2_content
    assert "M1" in m2_content, f"Expected M1 in M2 Depends On, got:\n{m2_content}"
    assert "Core Infrastructure" in m2_content


# ── _do_generate_milestone_knowledge: characterisation (R21) ──────────────────
# The cold-cache path, the uncached-milestone fallback, and the section-derived
# body fields were all reachable but unexercised. Pinned so the 65-statement
# function can be decomposed later (R8).

def _generate(workspace, number=1, repo="o/r"):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": repo}), \
         patch("extensions.gh_management.github_planner._resolve_repo", return_value=repo):
        return _do_generate_milestone_knowledge(number)


def test_generate_returns_init_error_when_uninitialised(workspace):
    """An uninitialised workspace short-circuits with the init guidance."""
    sentinel = {"status": "needs_init"}
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=sentinel):
        assert _do_generate_milestone_knowledge(1) == sentinel


def test_generate_falls_back_to_mn_title_when_milestone_not_cached(workspace):
    """With no cached milestone entry the title degrades to 'M<n>'."""
    _PROJECT_DOCS_CACHE["o/r"] = {"summary": "", "detail": "", "loaded_at": 0.0}
    result = _generate(workspace, 3)

    assert "error" not in result
    content = _milestone_knowledge_path(workspace, 3).read_text(encoding="utf-8")
    assert "# M3 — M3" in content


def test_generate_reads_docs_from_disk_when_cache_is_cold(workspace):
    """With no _PROJECT_DOCS_CACHE entry, project docs are read from disk and
    their H2 sections populate the generated body."""
    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir

    docs = _gh_planner_docs_dir(workspace)
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "project_summary.md").write_text(
        "## Design Principles\n- keep it small\n\n"
        "## Planned Features\n- caching layer\n- audit log\n",
        encoding="utf-8",
    )
    (docs / "project_detail.md").write_text(
        "## Caching\ndetails\n\n## Audit\ndetails\n", encoding="utf-8"
    )
    _MILESTONE_CACHE["o/r"] = [
        {"number": 1, "title": "First", "description": "d", "open_issues": 0}
    ]

    result = _generate(workspace, 1)

    assert "error" not in result
    content = _milestone_knowledge_path(workspace, 1).read_text(encoding="utf-8")
    assert "keep it small" in content, "design principles came from disk"
    assert "- caching layer" in content, "planned features came from disk"
    assert "- Caching" in content and "- Audit" in content, "detail H2s became the contract"


def test_generate_links_adjacent_milestones_from_the_index(workspace):
    """A milestone with neighbours in the index reports both depends-on and
    enables, rather than the first/last placeholders."""
    _PROJECT_DOCS_CACHE["o/r"] = {"summary": "", "detail": "", "loaded_at": 0.0}
    _MILESTONE_CACHE["o/r"] = [
        {"number": n, "title": t, "description": "", "open_issues": 0}
        for n, t in [(1, "Foundation"), (2, "Middle"), (3, "Finish")]
    ]
    _generate(workspace, 1)
    _generate(workspace, 3)

    _generate(workspace, 2)
    content = _milestone_knowledge_path(workspace, 2).read_text(encoding="utf-8")

    assert "M1 — Foundation" in content
    assert "M3 — Finish" in content
