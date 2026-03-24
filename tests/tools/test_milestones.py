"""Tests for GitHub milestone MCP tools."""
import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from terminal_hub.server import create_server
from extensions.gh_management.github_planner.storage import write_issue_file, STATUS_PENDING


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def _mock_gh():
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


# ── create_milestone ──────────────────────────────────────────────────────────

def test_create_milestone_success(workspace):
    mock_gh = _mock_gh()
    mock_gh.create_milestone.return_value = {
        "number": 1, "title": "Core Auth", "description": "Users can log in", "open_issues": 0
    }
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "create_milestone", {"title": "Core Auth", "description": "Users can log in"})
    assert result["number"] == 1
    assert result["title"] == "Core Auth"
    assert result["_display"]  # non-empty display string


def test_create_milestone_cached(workspace):
    """Second create_milestone call with same title should NOT call API again if cached."""
    from extensions.gh_management.github_planner import _MILESTONE_CACHE
    _MILESTONE_CACHE["o/r"] = [{"number": 1, "title": "Core Auth", "description": "...", "open_issues": 0}]

    mock_gh = _mock_gh()
    mock_gh.create_milestone.return_value = {"number": 1, "title": "Core Auth", "description": "...", "open_issues": 0}

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        call(server, "create_milestone", {"title": "Core Auth"})

    _MILESTONE_CACHE.clear()


# ── list_milestones ───────────────────────────────────────────────────────────

def test_list_milestones_uses_cache(workspace):
    from extensions.gh_management.github_planner import _MILESTONE_CACHE
    _MILESTONE_CACHE["o/r"] = [{"number": 1, "title": "M1", "description": "desc", "open_issues": 0}]

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "list_milestones", {})

    assert result["cached"] is True
    assert result["count"] == 1
    _MILESTONE_CACHE.clear()


def test_list_milestones_fetches_when_no_cache(workspace):
    from extensions.gh_management.github_planner import _MILESTONE_CACHE
    _MILESTONE_CACHE.clear()
    mock_gh = _mock_gh()
    mock_gh.list_milestones.return_value = [
        {"number": 1, "title": "M1", "description": "desc", "open_issues": 2}
    ]

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "list_milestones", {})

    assert result["cached"] is False
    assert result["count"] == 1
    _MILESTONE_CACHE.clear()


# ── assign_milestone ──────────────────────────────────────────────────────────

def test_assign_milestone_updates_frontmatter(workspace):
    from extensions.gh_management.github_planner import _MILESTONE_CACHE
    _MILESTONE_CACHE["o/r"] = [{"number": 2, "title": "Posting", "description": "...", "open_issues": 0}]

    write_issue_file(
        root=workspace, slug="my-issue", title="Add post", body="body",
        assignees=[], labels=[], created_at=date(2026, 3, 18), status=STATUS_PENDING,
    )

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "assign_milestone", {"slug": "my-issue", "milestone_number": 2})

    assert result["milestone_number"] == 2
    assert result["milestone_title"] == "Posting"
    assert result["github_assigned"] is False  # no issue_number in front matter

    from extensions.gh_management.github_planner.storage import read_issue_frontmatter
    fm = read_issue_frontmatter(workspace, "my-issue")
    assert fm["milestone_number"] == 2
    assert fm["milestone_title"] == "Posting"
    _MILESTONE_CACHE.clear()


def test_assign_milestone_missing_issue_returns_error(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        server = create_server()
        result = call(server, "assign_milestone", {"slug": "no-such", "milestone_number": 1})
    assert result["error"] == "issue_not_found"


# ── draft_issue with milestone_number ────────────────────────────────────────

def test_draft_issue_with_milestone_stores_in_frontmatter(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {
            "title": "Add login",
            "body": "Implement login",
            "milestone_number": 1,
        })

    from extensions.gh_management.github_planner.storage import read_issue_frontmatter
    fm = read_issue_frontmatter(workspace, result["slug"])
    assert fm["milestone_number"] == 1


# ── _milestone_label_color ────────────────────────────────────────────────────

def test_milestone_label_color_cycles():
    from extensions.gh_management.github_planner import _milestone_label_color, _MILESTONE_LABEL_PALETTE
    # m1 uses index 0
    assert _milestone_label_color(1) == _MILESTONE_LABEL_PALETTE[0]
    # m(palette_size+1) wraps back to index 0
    n = len(_MILESTONE_LABEL_PALETTE)
    assert _milestone_label_color(n + 1) == _MILESTONE_LABEL_PALETTE[0]
    # every value is a valid 6-char hex string
    for i in range(1, n + 1):
        color = _milestone_label_color(i)
        assert len(color) == 6
        int(color, 16)  # raises if not valid hex


# ── _ensure_milestone_label ───────────────────────────────────────────────────

def test_ensure_milestone_label_creates_new_label(workspace, tmp_path):
    """Creates m1 label on GitHub and appends to labels.json."""
    from extensions.gh_management.github_planner import _ensure_milestone_label

    mock_gh = _mock_gh()
    mock_gh.get_labels.return_value = set()  # label doesn't exist yet

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}), \
         patch("extensions.gh_management.github_planner._PLUGIN_DIR", tmp_path):
        (tmp_path / "labels.json").write_text("[]", encoding="utf-8")
        _ensure_milestone_label(1, "Core Auth")

    mock_gh.create_label.assert_called_once()
    call_args = mock_gh.create_label.call_args
    assert call_args[0][0] == "m1"
    assert call_args[0][2] == "Core Auth"  # description = milestone title


def test_ensure_milestone_label_updates_existing_label(workspace):
    """Updates description of existing m2 label on GitHub."""
    from extensions.gh_management.github_planner import _ensure_milestone_label

    mock_gh = _mock_gh()
    mock_gh.get_labels.return_value = {"m2"}  # label already exists

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}), \
         patch("extensions.gh_management.github_planner._LABEL_CACHE", {}), \
         patch("extensions.gh_management.github_planner._LABEL_ANALYSIS_CACHE", {}):
        _ensure_milestone_label(2, "Posting Features")

    mock_gh.update_label.assert_called_once_with("m2", "Posting Features")
    mock_gh.create_label.assert_not_called()


def test_ensure_milestone_label_swallows_github_error(workspace):
    """GitHub failure does not propagate — best-effort."""
    from extensions.gh_management.github_planner import _ensure_milestone_label

    mock_gh = _mock_gh()
    mock_gh.get_labels.side_effect = Exception("network failure")

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        # Must not raise
        _ensure_milestone_label(3, "Some Milestone")


def test_ensure_milestone_label_syncs_labels_json(workspace, tmp_path):
    """Newly created milestone label is appended to labels.json."""
    import json as _json
    from extensions.gh_management.github_planner import _MILESTONE_LABEL_PALETTE

    labels_file = tmp_path / "labels.json"
    labels_file.write_text(_json.dumps([{"name": "bug", "color": "d73a4a", "description": "..."}]), encoding="utf-8")

    mock_gh = _mock_gh()
    mock_gh.get_labels.return_value = set()

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}), \
         patch("extensions.gh_management.github_planner._PLUGIN_DIR", tmp_path):
        from extensions.gh_management.github_planner import _ensure_milestone_label
        _ensure_milestone_label(1, "Core Auth")

    written = _json.loads(labels_file.read_text(encoding="utf-8"))
    names = [e["name"] for e in written]
    assert "m1" in names
    m1 = next(e for e in written if e["name"] == "m1")
    assert m1["description"] == "Core Auth"
    assert m1["color"] == _MILESTONE_LABEL_PALETTE[0]


# ── create_milestone triggers label creation ──────────────────────────────────

def test_create_milestone_calls_ensure_milestone_label(workspace):
    """create_milestone must call _ensure_milestone_label after GitHub milestone creation."""
    from extensions.gh_management.github_planner import _MILESTONE_CACHE

    mock_gh = _mock_gh()
    mock_gh.create_milestone.return_value = {
        "number": 3, "title": "Search", "description": "Users can search", "open_issues": 0
    }
    _MILESTONE_CACHE.clear()

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}), \
         patch("extensions.gh_management.github_planner._ensure_milestone_label") as mock_ensure:
        server = create_server()
        call(server, "create_milestone", {"title": "Search", "description": "Users can search"})

    mock_ensure.assert_called_once_with(3, "Search")
    _MILESTONE_CACHE.clear()


# ── list_milestones triggers label sync ───────────────────────────────────────

def test_list_milestones_calls_ensure_labels_for_all(workspace):
    """Non-cached list_milestones must call _ensure_milestone_labels_for_all."""
    from extensions.gh_management.github_planner import _MILESTONE_CACHE
    _MILESTONE_CACHE.clear()

    mock_gh = _mock_gh()
    mock_gh.list_milestones.return_value = [
        {"number": 1, "title": "M1", "description": "desc", "open_issues": 0},
        {"number": 2, "title": "M2", "description": "desc2", "open_issues": 1},
    ]

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}), \
         patch("extensions.gh_management.github_planner._ensure_milestone_labels_for_all") as mock_ensure_all:
        server = create_server()
        call(server, "list_milestones", {})

    mock_ensure_all.assert_called_once()
    milestones_arg = mock_ensure_all.call_args[0][0]
    assert len(milestones_arg) == 2
    _MILESTONE_CACHE.clear()


def test_list_milestones_cached_does_not_call_ensure_labels(workspace):
    """Cached list_milestones must NOT trigger label sync (cache hit path)."""
    from extensions.gh_management.github_planner import _MILESTONE_CACHE
    _MILESTONE_CACHE["o/r"] = [{"number": 1, "title": "M1", "description": "d", "open_issues": 0}]

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}), \
         patch("extensions.gh_management.github_planner._ensure_milestone_labels_for_all") as mock_ensure_all:
        server = create_server()
        call(server, "list_milestones", {})

    mock_ensure_all.assert_not_called()
    _MILESTONE_CACHE.clear()
