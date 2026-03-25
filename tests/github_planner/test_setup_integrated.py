"""Tests for github_planner.setup — integrated bootstrap functions."""
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest


# ── _do_bootstrap_gh_plan ─────────────────────────────────────────────────────

def test_bootstrap_gh_plan_basic(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_gh_plan

    mock_milestones = [{"number": 1, "title": "M1 — Core"}]
    mock_issues = [
        {"slug": "1", "issue_number": 101, "title": "Issue A", "labels": ["feature"], "milestone_number": 1},
        {"slug": "2", "issue_number": 102, "title": "Issue B", "labels": [], "milestone_number": None},
    ]

    with patch("terminal_hub.workspace.set_active_project_root"), \
         patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.session._do_confirm_session_repo",
               return_value={"confirmed": True, "repo": "owner/repo"}), \
         patch("extensions.gh_management.github_planner.milestones._do_list_milestones",
               return_value={"milestones": mock_milestones}), \
         patch("extensions.gh_management.github_planner.issues._do_sync_github_issues",
               return_value={"synced": 2, "skipped": 0}), \
         patch("extensions.gh_management.github_planner.issues._do_list_issues",
               return_value={"issues": mock_issues}):
        result = _do_bootstrap_gh_plan(str(tmp_path))

    assert result["workspace_ready"] is True
    assert result["issue_count"] == 2
    assert result["confirmed_repo"] == "owner/repo"
    assert "M1 — Core" in result["landscape_display"]
    assert "Unassigned" in result["landscape_display"]
    assert "gh-plan ready" in result["_display"]


def test_bootstrap_gh_plan_skip_confirm(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_gh_plan

    with patch("terminal_hub.workspace.set_active_project_root"), \
         patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.milestones._do_list_milestones",
               return_value={"milestones": []}), \
         patch("extensions.gh_management.github_planner.issues._do_sync_github_issues",
               return_value={"synced": 0}), \
         patch("extensions.gh_management.github_planner.issues._do_list_issues",
               return_value={"issues": []}), \
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
         patch("extensions.gh_management.github_planner.issues._do_list_issues",
               return_value={"issues": []}):
        result = _do_bootstrap_gh_plan(str(tmp_path), sync_issues=False)

    mock_sync.assert_not_called()


def test_bootstrap_gh_plan_milestone_grouping(tmp_path):
    from extensions.gh_management.github_planner.setup import _do_bootstrap_gh_plan

    milestones = [{"number": 2, "title": "M2"}, {"number": 1, "title": "M1"}]
    issues = [
        {"slug": "1", "issue_number": 1, "title": "A", "labels": [], "milestone_number": 2},
        {"slug": "2", "issue_number": 2, "title": "B", "labels": ["bug"], "milestone_number": 1},
    ]

    with patch("terminal_hub.workspace.set_active_project_root"), \
         patch("extensions.gh_management.github_planner.setup.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.github_planner.session._do_confirm_session_repo",
               return_value={"confirmed": True, "repo": "r"}), \
         patch("extensions.gh_management.github_planner.milestones._do_list_milestones",
               return_value={"milestones": milestones}), \
         patch("extensions.gh_management.github_planner.issues._do_sync_github_issues",
               return_value={}), \
         patch("extensions.gh_management.github_planner.issues._do_list_issues",
               return_value={"issues": issues}):
        result = _do_bootstrap_gh_plan(str(tmp_path))

    display = result["landscape_display"]
    assert display.index("M1") < display.index("M2")


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
