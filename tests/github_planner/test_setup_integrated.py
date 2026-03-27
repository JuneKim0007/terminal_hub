"""Tests for github_planner.setup — integrated bootstrap functions."""
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest


# ── _do_bootstrap_gh_plan ─────────────────────────────────────────────────────

def _patch_bootstrap(tmp_path, lean_issues, milestones=None, confirm_result=None, sync_result=None):
    """Shared patch context for _do_bootstrap_gh_plan tests."""
    from unittest.mock import patch
    return [
        patch("terminal_hub.workspace.set_active_project_root"),
        patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path),
        patch("extensions.gh_management.github_planner.session._do_confirm_session_repo",
              return_value=confirm_result or {"confirmed": True, "repo": "owner/repo"}),
        patch("extensions.gh_management.github_planner.milestones._do_list_milestones",
              return_value={"milestones": milestones or []}),
        patch("extensions.gh_management.github_planner.issues._do_sync_github_issues",
              return_value=sync_result or {"synced": 0}),
        patch("extensions.gh_management.github_planner.storage.list_issue_titles",
              return_value=lean_issues),
    ]


def test_bootstrap_gh_plan_basic(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_gh_plan

    lean_issues = [
        {"slug": "1", "issue_number": 101, "title": "Issue A", "labels": ["feature"], "milestone_number": 1, "created_at": "2026-01-02"},
        {"slug": "2", "issue_number": 102, "title": "Issue B", "labels": [], "milestone_number": None, "created_at": "2026-01-01"},
    ]
    milestones = [{"number": 1, "title": "M1 — Core"}]

    patches = _patch_bootstrap(tmp_path, lean_issues, milestones=milestones, sync_result={"synced": 2, "skipped": 0})
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        result = _do_bootstrap_gh_plan(str(tmp_path))

    assert result["workspace_ready"] is True
    assert result["issue_count"] == 2
    assert result["confirmed_repo"] == "owner/repo"
    assert "M1 — Core" in result["landscape_display"]
    assert "Unassigned" in result["landscape_display"]
    assert "gh-plan ready" in result["_display"]
    # Default response must NOT include full issue objects
    assert "issues" not in result
    assert result["issue_slugs"] == ["1", "2"]


def test_bootstrap_gh_plan_skip_confirm(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_gh_plan

    with patch("terminal_hub.workspace.set_active_project_root"), \
         patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.milestones._do_list_milestones",
               return_value={"milestones": []}), \
         patch("extensions.gh_management.github_planner.issues._do_sync_github_issues",
               return_value={"synced": 0}), \
         patch("extensions.gh_management.github_planner.storage.list_issue_titles",
               return_value=[]), \
         patch("extensions.gh_management.github_planner.session._do_confirm_session_repo") as mock_confirm:
        result = _do_bootstrap_gh_plan(str(tmp_path), confirm_repo=False)

    mock_confirm.assert_not_called()
    assert result["confirmed_repo"] is None
    assert result["landscape_display"] == "No open issues."


def test_bootstrap_gh_plan_skip_sync(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_gh_plan

    with patch("terminal_hub.workspace.set_active_project_root"), \
         patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.session._do_confirm_session_repo",
               return_value={"confirmed": True, "repo": "owner/repo"}), \
         patch("extensions.gh_management.github_planner.milestones._do_list_milestones",
               return_value={"milestones": []}), \
         patch("extensions.gh_management.github_planner.issues._do_sync_github_issues") as mock_sync, \
         patch("extensions.gh_management.github_planner.storage.list_issue_titles",
               return_value=[]):
        result = _do_bootstrap_gh_plan(str(tmp_path), sync_issues=False)

    mock_sync.assert_not_called()


def test_bootstrap_gh_plan_milestone_grouping(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_gh_plan

    milestones = [{"number": 2, "title": "M2"}, {"number": 1, "title": "M1"}]
    lean_issues = [
        {"slug": "1", "issue_number": 1, "title": "A", "labels": [], "milestone_number": 2, "created_at": "2026-01-02"},
        {"slug": "2", "issue_number": 2, "title": "B", "labels": ["bug"], "milestone_number": 1, "created_at": "2026-01-01"},
    ]

    with patch("terminal_hub.workspace.set_active_project_root"), \
         patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.session._do_confirm_session_repo",
               return_value={"confirmed": True, "repo": "r"}), \
         patch("extensions.gh_management.github_planner.milestones._do_list_milestones",
               return_value={"milestones": milestones}), \
         patch("extensions.gh_management.github_planner.issues._do_sync_github_issues",
               return_value={}), \
         patch("extensions.gh_management.github_planner.storage.list_issue_titles",
               return_value=lean_issues):
        result = _do_bootstrap_gh_plan(str(tmp_path))

    display = result["landscape_display"]
    assert display.index("M1") < display.index("M2")


def test_bootstrap_gh_plan_full_data_includes_issues(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_gh_plan

    lean_issues = [
        {"slug": "1", "issue_number": 10, "title": "T", "labels": [], "milestone_number": None, "created_at": "2026-01-01"},
    ]
    full_issues = [{"slug": "1", "issue_number": 10, "title": "T", "labels": [], "status": "open"}]

    with patch("terminal_hub.workspace.set_active_project_root"), \
         patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.session._do_confirm_session_repo",
               return_value={"confirmed": True, "repo": "r"}), \
         patch("extensions.gh_management.github_planner.milestones._do_list_milestones",
               return_value={"milestones": []}), \
         patch("extensions.gh_management.github_planner.issues._do_sync_github_issues",
               return_value={}), \
         patch("extensions.gh_management.github_planner.storage.list_issue_titles",
               return_value=lean_issues), \
         patch("extensions.gh_management.github_planner.issues._do_list_issues",
               return_value={"issues": full_issues}):
        result = _do_bootstrap_gh_plan(str(tmp_path), full_data=True)

    assert "issues" in result
    assert result["issues"] == full_issues
    assert result["issue_slugs"] == ["1"]


# ── _do_bootstrap_new_repo ────────────────────────────────────────────────────

def test_bootstrap_new_repo_success(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_new_repo

    with patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.project_docs._do_update_project_description",
               return_value={"ok": True}), \
         patch("extensions.gh_management.github_planner.workspace_tools._do_create_github_repo",
               return_value={"github_repo": "owner/myproject", "url": "https://github.com/owner/myproject"}), \
         patch("extensions.gh_management.github_planner.workspace_tools._do_set_preference"), \
         patch("extensions.gh_management.github_planner.session._do_set_session_repo",
               return_value={"confirmed": True}), \
         patch("extensions.gh_management.github_planner.labels._do_list_repo_labels",
               return_value={"labels": [{"name": "bug"}, {"name": "feature"}]}), \
         patch("extensions.gh_management.github_planner.milestones._do_list_milestones",
               return_value={"milestones": [{"number": 1}]}):
        result = _do_bootstrap_new_repo(
            project_title="My Project",
            project_description="A test project",
            tech_stack=["Python", "FastAPI"],
            design_principles=["Keep it simple"],
        )

    assert result["repo_created"] is True
    assert result["project_description_saved"] is True
    assert result["ready_to_plan"] is True
    assert result["caches_warmed"]["labels"] == 2
    assert result["caches_warmed"]["milestones"] == 1
    assert "Repo created" in result["_display"]


def test_bootstrap_new_repo_create_fails(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_new_repo

    with patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.project_docs._do_update_project_description",
               return_value={"ok": True}), \
         patch("extensions.gh_management.github_planner.workspace_tools._do_create_github_repo",
               return_value={"error": "auth_failed", "message": "Not authenticated"}):
        result = _do_bootstrap_new_repo(
            project_title="My Project",
            project_description="desc",
            tech_stack=[],
            design_principles=[],
        )

    assert result["repo_created"] is False
    assert "error" in result
    assert result["project_description_saved"] is True


def test_bootstrap_new_repo_slugifies_title(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_new_repo

    captured = {}

    def fake_create(name, description, private):
        captured["name"] = name
        return {"github_repo": f"owner/{name}", "url": "https://github.com/owner/my-project"}

    with patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.project_docs._do_update_project_description",
               return_value={}), \
         patch("extensions.gh_management.github_planner.workspace_tools._do_create_github_repo",
               side_effect=fake_create), \
         patch("extensions.gh_management.github_planner.workspace_tools._do_set_preference"), \
         patch("extensions.gh_management.github_planner.session._do_set_session_repo", return_value={}), \
         patch("extensions.gh_management.github_planner.labels._do_list_repo_labels",
               return_value={"labels": []}), \
         patch("extensions.gh_management.github_planner.milestones._do_list_milestones",
               return_value={"milestones": []}):
        _do_bootstrap_new_repo("My Project", "desc", [], [])

    assert captured["name"] == "my-project"
