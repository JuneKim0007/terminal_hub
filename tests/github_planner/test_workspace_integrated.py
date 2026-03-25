"""Tests for workspace_tools integrated session functions."""
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest


# ── _do_initialize_implementation_session ────────────────────────────────────

def test_initialize_implementation_session_with_issues(tmp_path):
    from extensions.gh_management.github_planner.workspace_tools import _do_initialize_implementation_session

    mock_issues = [{"slug": "1", "title": "Fix bug"}]

    pkg_mock = MagicMock()
    pkg_mock.get_workspace_root.return_value = tmp_path

    with patch("terminal_hub.workspace.set_active_project_root"), \
         patch("extensions.gh_management.github_planner.workspace_tools._pkg", return_value=pkg_mock), \
         patch("extensions.gh_management.github_planner.workspace_tools._do_apply_unload_policy",
               return_value={"cleared": ["label_cache"]}), \
         patch("extensions.gh_management.github_planner.session._do_confirm_session_repo",
               return_value={"confirmed": True, "repo": "owner/repo"}), \
         patch("extensions.gh_management.github_planner.project_docs._do_load_project_docs",
               return_value={"summary": "Project summary text"}), \
         patch("extensions.gh_management.github_planner.issues._do_list_issues",
               return_value={"issues": mock_issues}):
        result = _do_initialize_implementation_session(str(tmp_path))

    assert result["workspace_ready"] is True
    assert result["issue_count"] == 1
    assert result["next_action"] == "select_issue"
    assert result["repo_confirmed"] == "owner/repo"
    assert "Implementation session ready" in result["_display"]


def test_initialize_implementation_session_no_issues(tmp_path):
    from extensions.gh_management.github_planner.workspace_tools import _do_initialize_implementation_session

    pkg_mock = MagicMock()
    pkg_mock.get_workspace_root.return_value = tmp_path

    with patch("terminal_hub.workspace.set_active_project_root"), \
         patch("extensions.gh_management.github_planner.workspace_tools._pkg", return_value=pkg_mock), \
         patch("extensions.gh_management.github_planner.workspace_tools._do_apply_unload_policy",
               return_value={"cleared": []}), \
         patch("extensions.gh_management.github_planner.session._do_confirm_session_repo",
               return_value={"confirmed": False, "repo": None}), \
         patch("extensions.gh_management.github_planner.project_docs._do_load_project_docs",
               return_value={"summary": ""}), \
         patch("extensions.gh_management.github_planner.issues._do_list_issues",
               return_value={"issues": []}):
        result = _do_initialize_implementation_session(str(tmp_path), previous_command="gh-plan")

    assert result["next_action"] == "fetch_from_github"
    assert result["issue_count"] == 0


# ── _do_load_implementation_context ──────────────────────────────────────────

def test_load_implementation_context_success(tmp_path):
    from extensions.gh_management.github_planner.workspace_tools import _do_load_implementation_context

    session_result = {
        "workspace_ready": True,
        "cache_cleared": [],
        "repo_confirmed": "owner/repo",
        "project_summary": "summary",
        "issues": [],
        "issue_count": 0,
        "next_action": "select_issue",
        "_display": "ready",
    }
    issue_result = {
        "slug": "42",
        "title": "Fix thing",
        "content": "## body",
        "labels": ["bug"],
        "agent_workflow": ["Step 1", "Step 2"],
    }

    with patch("extensions.gh_management.github_planner.workspace_tools._do_initialize_implementation_session",
               return_value=session_result), \
         patch("extensions.gh_management.gh_implementation._do_load_active_issue",
               return_value=issue_result):
        result = _do_load_implementation_context(str(tmp_path), "42", lookup_design_refs=False)

    assert result["context_ready"] is True
    assert result["has_agent_workflow"] is True
    assert result["issue_content"]["slug"] == "42"


def test_load_implementation_context_issue_not_found(tmp_path):
    from extensions.gh_management.github_planner.workspace_tools import _do_load_implementation_context

    session_result = {"workspace_ready": True, "issues": [], "issue_count": 0}
    error_result = {"error": "issue_not_found", "message": "No issue for slug '99'"}

    with patch("extensions.gh_management.github_planner.workspace_tools._do_initialize_implementation_session",
               return_value=session_result), \
         patch("extensions.gh_management.gh_implementation._do_load_active_issue",
               return_value=error_result):
        result = _do_load_implementation_context(str(tmp_path), "99")

    assert result["context_ready"] is False
    assert "error" in result


def test_load_implementation_context_design_refs_extracted(tmp_path):
    from extensions.gh_management.github_planner.workspace_tools import _do_load_implementation_context

    session_result = {
        "workspace_ready": True, "repo_confirmed": "r", "project_summary": "",
        "issues": [], "issue_count": 0,
    }
    issue_result = {
        "slug": "5",
        "agent_workflow": ["project_detail.md § Feature Auth", "plain step"],
    }

    with patch("extensions.gh_management.github_planner.workspace_tools._do_initialize_implementation_session",
               return_value=session_result), \
         patch("extensions.gh_management.gh_implementation._do_load_active_issue",
               return_value=issue_result), \
         patch("extensions.gh_management.github_planner.project_docs._do_lookup_feature_section",
               return_value={"section": "Auth section content"}) as mock_lookup:
        result = _do_load_implementation_context(str(tmp_path), "5", lookup_design_refs=True)

    mock_lookup.assert_called_once_with("Feature Auth")
    assert result["design_sections"]["Feature Auth"] == "Auth section content"


def test_load_implementation_context_no_design_refs_when_flag_false(tmp_path):
    from extensions.gh_management.github_planner.workspace_tools import _do_load_implementation_context

    session_result = {"workspace_ready": True, "issues": [], "issue_count": 0}
    issue_result = {"slug": "7", "agent_workflow": ["project_detail.md § Some Section"]}

    with patch("extensions.gh_management.github_planner.workspace_tools._do_initialize_implementation_session",
               return_value=session_result), \
         patch("extensions.gh_management.gh_implementation._do_load_active_issue",
               return_value=issue_result), \
         patch("extensions.gh_management.github_planner.project_docs._do_lookup_feature_section") as mock_lookup:
        result = _do_load_implementation_context(str(tmp_path), "7", lookup_design_refs=False)

    mock_lookup.assert_not_called()
    assert result["design_sections"] == {}
