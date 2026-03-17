"""Tests for draft_issue and submit_issue MCP tools."""
import asyncio
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from terminal_hub.server import create_server
from extensions.github_planner.storage import STATUS_OPEN, STATUS_PENDING, write_issue_file


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def _mock_gh(number=1, url="https://github.com/o/r/issues/1"):
    mock = MagicMock()
    mock.create_issue.return_value = {"number": number, "html_url": url}
    mock.ensure_labels.return_value = None
    return mock


# ── draft_issue ───────────────────────────────────────────────────────────────

def test_draft_issue_creates_pending_local_file(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {"title": "Fix auth bug", "body": "Fix it."})
    assert result["status"] == STATUS_PENDING
    assert (workspace / "hub_agents" / "issues" / "fix-auth-bug.md").exists()


def test_draft_issue_returns_slug_and_preview(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {"title": "Add feature", "body": "Nice feature."})
    assert result["slug"] == "add-feature"
    assert "Nice feature" in result["preview_body"]


def test_draft_issue_truncates_long_body_in_preview(workspace):
    long_body = "x" * 500
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {"title": "Big issue", "body": long_body})
    assert len(result["preview_body"]) <= 304  # 300 + ellipsis


def test_draft_issue_missing_title_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {"title": "", "body": "no title here"})
    assert result["error"] == "draft_failed"
    assert "title" in result["message"]
    assert result["_hook"] is None


def test_draft_issue_missing_body_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {"title": "No body", "body": ""})
    assert result["error"] == "draft_failed"
    assert "body" in result["message"]


def test_draft_issue_resolves_slug_collision(workspace):
    (workspace / "hub_agents" / "issues" / "fix-auth-bug.md").write_text("x")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {"title": "Fix auth bug", "body": "body"})
    assert result["slug"] == "fix-auth-bug-2"


def test_draft_issue_stores_labels_and_assignees(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {
            "title": "Tagged issue", "body": "body",
            "labels": ["bug"], "assignees": ["alice"],
        })
    assert result["labels"] == ["bug"]
    assert result["assignees"] == ["alice"]


def test_draft_issue_display_shows_title(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {"title": "My Task", "body": "body"})
    assert "_display" in result
    assert "My Task" in result["_display"]


# ── submit_issue ──────────────────────────────────────────────────────────────

def _make_pending(workspace, slug="my-issue", title="My Issue", body="body", labels=None):
    write_issue_file(
        root=workspace, slug=slug, title=title, body=body,
        assignees=[], labels=labels or [],
        created_at=date(2026, 3, 15), status=STATUS_PENDING,
    )


def test_submit_issue_success_returns_number_and_url(workspace):
    _make_pending(workspace)
    with patch("extensions.github_planner.get_github_client", return_value=(_mock_gh(99, "https://gh/99"), "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "my-issue"})
    assert result["issue_number"] == 99
    assert "gh/99" in result["url"]
    assert "_display" in result
    assert "99" in result["_display"]


def test_submit_issue_success_display_absent_in_errors(workspace):
    with patch("extensions.github_planner.get_github_client", return_value=(_mock_gh(), "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "no-such-slug"})
    assert result.get("error") == "submit_failed"
    assert "_display" not in result


def test_submit_issue_updates_local_file_to_open(workspace):
    _make_pending(workspace)
    with patch("extensions.github_planner.get_github_client", return_value=(_mock_gh(5, "https://gh/5"), "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "submit_issue", {"slug": "my-issue"})

    from extensions.github_planner.storage import read_issue_frontmatter
    fm = read_issue_frontmatter(workspace, "my-issue")
    assert fm["status"] == STATUS_OPEN
    assert fm["issue_number"] == 5


def test_submit_issue_not_found_returns_error(workspace):
    with patch("extensions.github_planner.get_github_client", return_value=(_mock_gh(), "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "no-such-slug"})
    assert result["error"] == "submit_failed"
    assert result["_hook"] is None


def test_submit_issue_no_auth_returns_error(workspace):
    _make_pending(workspace)
    with patch("extensions.github_planner.get_github_client", return_value=(None, "No auth.")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "my-issue"})
    assert result["error"] == "github_unavailable"
    assert result["_hook"] is None


def test_submit_issue_label_bootstrap_failed_returns_error(workspace):
    _make_pending(workspace, labels=["unknown-label"])
    mock_gh = _mock_gh()
    mock_gh.ensure_labels.return_value = "Labels not found and could not be created: unknown-label"
    with patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "my-issue"})
    assert result["error"] == "label_bootstrap_failed"
    assert result["_hook"] is None


def test_submit_issue_github_error_returns_error(workspace):
    from extensions.github_planner.client import GitHubError
    _make_pending(workspace)
    mock_gh = MagicMock()
    mock_gh.ensure_labels.return_value = None
    mock_gh.create_issue.side_effect = GitHubError("token rejected", error_code="auth_failed")
    with patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "my-issue"})
    assert result["error"] == "auth_failed"
    assert result["_hook"] is None


# ── draft_issue: empty slug from title (line 134-135 in __init__.py) ──────────

def test_draft_issue_empty_slug_from_special_char_title(workspace):
    """Line 134-135: slugify('---') → '' → returns draft_failed error."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {"title": "---", "body": "some body"})
    assert result["error"] == "draft_failed"
    assert "slug" in result["message"].lower() or "alphanumeric" in result["message"].lower()


def test_draft_issue_empty_slug_from_only_spaces(workspace):
    """Line 134-135: title of only whitespace slugifies to '' → draft_failed."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {"title": "   ", "body": "body"})
    assert result["error"] == "draft_failed"


# ── draft_issue: OSError on write (lines 175-176 in __init__.py) ──────────────

def test_draft_issue_oserror_on_write_returns_error(workspace):
    """Lines 175-176: OSError from write_issue_file → draft_failed error."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.write_issue_file", side_effect=OSError("disk full")):
        server = create_server()
        result = call(server, "draft_issue", {"title": "Valid Title", "body": "body"})
    assert result["error"] == "draft_failed"
    assert result["_hook"] is None


# ── submit_issue: invalid slug format (lines 246-247 in __init__.py) ──────────

def test_submit_issue_invalid_slug_format_returns_error(workspace):
    """Lines 246-247: slug fails validate_slug → submit_failed error."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "INVALID SLUG!!"})
    assert result["error"] == "submit_failed"
    assert result["_hook"] is None


# ── submit_issue: not initialized (line 242 in __init__.py) ───────────────────

def test_submit_issue_not_initialized_returns_needs_init(tmp_path):
    """Line 242: hub_agents/ absent → needs_init."""
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "some-slug"})
    assert result["status"] == "needs_init"


# ── draft_issue: not initialized (line 123 in __init__.py) ───────────────────

def test_draft_issue_not_initialized_returns_needs_init(tmp_path):
    """Line 123: hub_agents/ absent → needs_init response from ensure_initialized."""
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "draft_issue", {"title": "My Title", "body": "body"})
    assert result["status"] == "needs_init"
