"""Tests for draft_issue and submit_issue MCP tools."""
import asyncio
import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from terminal_hub.server import create_server
from terminal_hub.storage import STATUS_OPEN, STATUS_PENDING, write_issue_file


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
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {
            "issue_json": json.dumps({"title": "Fix auth bug", "body": "Fix it."})
        })
    assert result["status"] == STATUS_PENDING
    assert (workspace / "hub_agents" / "issues" / "fix-auth-bug.md").exists()


def test_draft_issue_returns_slug_and_preview(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {
            "issue_json": json.dumps({"title": "Add feature", "body": "Nice feature."})
        })
    assert result["slug"] == "add-feature"
    assert "Nice feature" in result["preview_body"]


def test_draft_issue_truncates_long_body_in_preview(workspace):
    long_body = "x" * 500
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {
            "issue_json": json.dumps({"title": "Big issue", "body": long_body})
        })
    assert len(result["preview_body"]) <= 304  # 300 + ellipsis


def test_draft_issue_invalid_json_returns_error(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {"issue_json": "not json {{"})
    assert result["error"] == "draft_failed"
    assert result["_hook"] is None


def test_draft_issue_missing_title_returns_error(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {
            "issue_json": json.dumps({"body": "no title here"})
        })
    assert result["error"] == "draft_failed"
    assert "title" in result["message"]
    assert result["_hook"] is None


def test_draft_issue_missing_body_returns_error(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {
            "issue_json": json.dumps({"title": "No body"})
        })
    assert result["error"] == "draft_failed"
    assert "body" in result["message"]


def test_draft_issue_resolves_slug_collision(workspace):
    (workspace / "hub_agents" / "issues" / "fix-auth-bug.md").write_text("x")
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {
            "issue_json": json.dumps({"title": "Fix auth bug", "body": "body"})
        })
    assert result["slug"] == "fix-auth-bug-2"


def test_draft_issue_stores_labels_and_assignees(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "draft_issue", {
            "issue_json": json.dumps({
                "title": "Tagged issue", "body": "body",
                "labels": ["bug"], "assignees": ["alice"],
            })
        })
    assert result["labels"] == ["bug"]
    assert result["assignees"] == ["alice"]


# ── submit_issue ──────────────────────────────────────────────────────────────

def _make_pending(workspace, slug="my-issue", title="My Issue", body="body", labels=None):
    write_issue_file(
        root=workspace, slug=slug, title=title, body=body,
        assignees=[], labels=labels or [],
        created_at=date(2026, 3, 15), status=STATUS_PENDING,
    )


def test_submit_issue_success_returns_number_and_url(workspace):
    _make_pending(workspace)
    with patch("terminal_hub.server.get_github_client", return_value=(_mock_gh(99, "https://gh/99"), "")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "my-issue"})
    assert result["issue_number"] == 99
    assert "gh/99" in result["url"]
    assert "_display" in result
    assert "99" in result["_display"]


def test_submit_issue_success_display_absent_in_errors(workspace):
    with patch("terminal_hub.server.get_github_client", return_value=(_mock_gh(), "")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "no-such-slug"})
    assert result.get("error") == "submit_failed"
    assert "_display" not in result


def test_submit_issue_updates_local_file_to_open(workspace):
    _make_pending(workspace)
    with patch("terminal_hub.server.get_github_client", return_value=(_mock_gh(5, "https://gh/5"), "")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "submit_issue", {"slug": "my-issue"})

    from terminal_hub.storage import read_issue_frontmatter
    fm = read_issue_frontmatter(workspace, "my-issue")
    assert fm["status"] == STATUS_OPEN
    assert fm["issue_number"] == 5


def test_submit_issue_not_found_returns_error(workspace):
    with patch("terminal_hub.server.get_github_client", return_value=(_mock_gh(), "")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "no-such-slug"})
    assert result["error"] == "submit_failed"
    assert result["_hook"] is None


def test_submit_issue_no_auth_returns_error(workspace):
    _make_pending(workspace)
    with patch("terminal_hub.server.get_github_client", return_value=(None, "No auth.")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "my-issue"})
    assert result["error"] == "github_unavailable"
    assert result["_hook"] is None


def test_submit_issue_label_bootstrap_failed_returns_error(workspace):
    _make_pending(workspace, labels=["unknown-label"])
    mock_gh = _mock_gh()
    mock_gh.ensure_labels.return_value = "Labels not found and could not be created: unknown-label"
    with patch("terminal_hub.server.get_github_client", return_value=(mock_gh, "")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "my-issue"})
    assert result["error"] == "label_bootstrap_failed"
    assert result["_hook"] is None


def test_submit_issue_github_error_returns_error(workspace):
    from terminal_hub.github_client import GitHubError
    _make_pending(workspace)
    mock_gh = MagicMock()
    mock_gh.ensure_labels.return_value = None
    mock_gh.create_issue.side_effect = GitHubError("token rejected", error_code="auth_failed")
    with patch("terminal_hub.server.get_github_client", return_value=(mock_gh, "")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "my-issue"})
    assert result["error"] == "auth_failed"
    assert result["_hook"] is None
