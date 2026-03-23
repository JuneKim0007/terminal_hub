import asyncio
from datetime import date
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server
from extensions.gh_management.github_planner.storage import write_doc_file, write_issue_file


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def test_get_project_context_single(workspace):
    write_doc_file(workspace, "project_description", "# Project\n")
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_project_context", {"doc_key": "project_description"})
    assert result["content"] == "# Project\n"


def test_get_project_context_not_found(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_project_context", {"doc_key": "project_description"})
    assert result["content"] is None


def test_get_project_context_all(workspace):
    write_doc_file(workspace, "project_description", "# Project\n")
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_project_context", {"doc_key": "all"})
    assert result["project_description"] == "# Project\n"
    assert result["architecture"] is None


def test_get_issue_context_found(workspace):
    write_issue_file(root=workspace, slug="fix-bug", title="Fix bug",
                     body="body", assignees=[], labels=[], created_at=date(2026, 3, 15))
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_issue_context", {"slug": "fix-bug"})
    assert result["slug"] == "fix-bug"
    assert "Fix bug" in result["content"]


def test_get_issue_context_not_found(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_issue_context", {"slug": "no-such-issue"})
    assert result["error"] == "not_found"
    assert "no-such-issue" in result["message"]


# ── update_project_description: not initialized (line 258) ───────────────────

def test_update_project_description_not_initialized(tmp_path):
    """hub_agents/ absent → needs_init."""
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "update_project_description", {"title": "X", "description": "desc"})
    assert result["status"] == "needs_init"


# ── update_architecture: not initialized ──────────────────────────────────────

def test_update_architecture_not_initialized(tmp_path):
    """hub_agents/ absent → needs_init."""
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "update_architecture", {"overview": "layered arch"})
    assert result["status"] == "needs_init"


# ── get_project_context: not initialized (line 280) ──────────────────────────

def test_get_project_context_not_initialized(tmp_path):
    """Line 280: hub_agents/ absent → needs_init."""
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "get_project_context", {"doc_key": "project_description"})
    assert result["status"] == "needs_init"


# ── get_project_context: invalid doc_key (lines 288-289) ─────────────────────

def test_get_project_context_invalid_key_returns_error(workspace):
    """Lines 288-289: invalid doc_key → ValueError caught → not_found error."""
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_project_context", {"doc_key": "nonexistent_key"})
    assert result["error"] == "not_found"
    assert result["_hook"] is None


# ── get_issue_context: not initialized (line 242) ─────────────────────────────

def test_get_issue_context_not_initialized(tmp_path):
    """Line 242: hub_agents/ absent → needs_init."""
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "get_issue_context", {"slug": "some-issue"})
    assert result["status"] == "needs_init"


# ── get_issue_context: invalid slug format (lines 246-247) ───────────────────

def test_get_issue_context_invalid_slug_returns_error(workspace):
    """Lines 246-247: slug fails validate_slug → not_found error."""
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_issue_context", {"slug": "INVALID!!SLUG"})
    assert result["error"] == "not_found"
    assert result["_hook"] is None
