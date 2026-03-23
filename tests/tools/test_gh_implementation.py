"""Tests for gh_implementation extension tools."""
import asyncio
from pathlib import Path
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from terminal_hub.server import create_server
from extensions.gh_management.github_planner.storage import write_issue_file, STATUS_PENDING, STATUS_OPEN


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


# ── get_implementation_session ────────────────────────────────────────────────

def test_get_implementation_session_returns_defaults(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "get_implementation_session", {})
    assert result["close_automatically_on_gh"] is True
    assert result["delete_local_issue_on_gh"] is True
    assert "_display" in result


# ── set_implementation_session_flag ──────────────────────────────────────────

def test_set_flag_updates_value(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "set_implementation_session_flag", {"key": "close_automatically_on_gh", "value": False})
        result = call(server, "get_implementation_session", {})
    assert result["close_automatically_on_gh"] is False


def test_set_flag_unknown_key_returns_error(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "set_implementation_session_flag", {"key": "nonexistent", "value": True})
    assert result["error"] == "unknown_flag"


# ── update_issue_frontmatter ──────────────────────────────────────────────────

def test_update_issue_frontmatter_writes_fields(workspace):
    write_issue_file(
        root=workspace, slug="my-issue", title="Test", body="body",
        assignees=[], labels=[], created_at=date(2026, 3, 18), status=STATUS_PENDING,
    )
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_issue_frontmatter", {
            "slug": "my-issue",
            "fields": {"agent_workflow": ["Step A", "Step B"]},
        })
    assert result["slug"] == "my-issue"
    assert "agent_workflow" in result["updated_fields"]
    from extensions.gh_management.github_planner.storage import read_issue_frontmatter
    fm = read_issue_frontmatter(workspace, "my-issue")
    assert fm["agent_workflow"] == ["Step A", "Step B"]


def test_update_issue_frontmatter_missing_file_returns_error(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_issue_frontmatter", {"slug": "no-such", "fields": {"x": 1}})
    assert result["error"] == "issue_not_found"


# ── delete_local_issue ────────────────────────────────────────────────────────

def test_delete_local_issue_removes_file(workspace):
    write_issue_file(
        root=workspace, slug="to-delete", title="Delete me", body="body",
        assignees=[], labels=[], created_at=date(2026, 3, 18), status=STATUS_PENDING,
    )
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "delete_local_issue", {"slug": "to-delete"})
    assert result["deleted"] is True
    assert not (workspace / "hub_agents" / "issues" / "to-delete.md").exists()


def test_delete_local_issue_missing_returns_error(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "delete_local_issue", {"slug": "no-such"})
    assert result["error"] == "not_found"


# ── fetch_github_issues ───────────────────────────────────────────────────────

def test_fetch_github_issues_writes_files(workspace):
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues.return_value = [
        {"number": 1, "title": "First issue", "body": "body1", "labels": [], "assignees": [], "html_url": "https://github.com/o/r/issues/1"},
        {"number": 2, "title": "Second issue", "body": "body2", "labels": [{"name": "bug"}], "assignees": [], "html_url": "https://github.com/o/r/issues/2"},
    ]
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.gh_implementation.ensure_initialized", return_value=None):
        server = create_server()
        result = call(server, "fetch_github_issues", {"state": "open", "limit": 30})
    assert result["fetched"] == 2
    assert "1" in result["slugs"]
    assert (workspace / "hub_agents" / "issues" / "1.md").exists()
    assert (workspace / "hub_agents" / "issues" / "2.md").exists()


def test_fetch_github_issues_skips_existing(workspace):
    # Pre-create issue 1
    write_issue_file(
        root=workspace, slug="1", title="Existing", body="body",
        assignees=[], labels=[], created_at=date(2026, 3, 18), status=STATUS_OPEN,
    )
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues.return_value = [
        {"number": 1, "title": "Existing", "body": "body", "labels": [], "assignees": [], "html_url": ""},
    ]
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.gh_implementation.ensure_initialized", return_value=None):
        server = create_server()
        result = call(server, "fetch_github_issues", {})
    assert result["fetched"] == 0  # skipped because file already exists


# ── close_github_issue ────────────────────────────────────────────────────────

def test_close_github_issue_calls_api(workspace):
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.close_issue.return_value = {"number": 42, "state": "closed"}
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.gh_implementation.get_github_client", return_value=(mock_gh, None)), \
         patch("extensions.gh_management.gh_implementation.ensure_initialized", return_value=None):
        server = create_server()
        result = call(server, "close_github_issue", {"issue_number": 42})
    assert result["closed"] is True
    mock_gh.close_issue.assert_called_once_with(42, comment=None)


# ── load_active_issue / unload_active_issue ───────────────────────────────

class TestLoadActiveIssue:
    def test_load_found_issue(self, tmp_path, monkeypatch):
        # setup
        root = tmp_path
        issues_dir = root / "hub_agents" / "issues"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "7.md"
        issue_file.write_text(
            "---\ntitle: Fix the thing\nlabels:\n- bug\nagent_workflow:\n- step one\n---\n\nBody text here",
            encoding="utf-8",
        )
        monkeypatch.setattr("extensions.gh_management.gh_implementation.get_workspace_root", lambda: root)
        from extensions.gh_management.gh_implementation import _SESSION_FLAGS, _do_load_active_issue
        _SESSION_FLAGS.clear()

        result = _do_load_active_issue("7")

        assert result["slug"] == "7"
        assert result["title"] == "Fix the thing"
        assert result["labels"] == ["bug"]
        assert result["agent_workflow"] == ["step one"]
        assert "Body text here" in result["content"]
        assert _SESSION_FLAGS[str(root)]["active_issue_slug"] == "7"

    def test_load_missing_issue(self, tmp_path, monkeypatch):
        root = tmp_path
        (root / "hub_agents" / "issues").mkdir(parents=True)
        monkeypatch.setattr("extensions.gh_management.gh_implementation.get_workspace_root", lambda: root)
        from extensions.gh_management.gh_implementation import _SESSION_FLAGS, _do_load_active_issue
        _SESSION_FLAGS.clear()

        result = _do_load_active_issue("99")

        assert result["error"] == "issue_not_found"
        assert "99" not in str(_SESSION_FLAGS.get(str(root), {}).get("active_issue_slug", ""))


class TestUnloadActiveIssue:
    def _make_issue(self, root, slug="7"):
        issues_dir = root / "hub_agents" / "issues"
        issues_dir.mkdir(parents=True, exist_ok=True)
        f = issues_dir / f"{slug}.md"
        f.write_text("---\ntitle: T\n---\n", encoding="utf-8")
        return f

    def test_unload_with_delete(self, tmp_path, monkeypatch):
        root = tmp_path
        f = self._make_issue(root)
        monkeypatch.setattr("extensions.gh_management.gh_implementation.get_workspace_root", lambda: root)
        from extensions.gh_management.gh_implementation import _SESSION_FLAGS, _do_unload_active_issue
        _SESSION_FLAGS[str(root)] = {"active_issue_slug": "7", "delete_local_issue_on_gh": True}

        result = _do_unload_active_issue()

        assert result["unloaded"] is True
        assert result["file_deleted"] is True
        assert not f.exists()
        assert _SESSION_FLAGS[str(root)].get("active_issue_slug") is None

    def test_unload_without_delete(self, tmp_path, monkeypatch):
        root = tmp_path
        f = self._make_issue(root)
        monkeypatch.setattr("extensions.gh_management.gh_implementation.get_workspace_root", lambda: root)
        from extensions.gh_management.gh_implementation import _SESSION_FLAGS, _do_unload_active_issue
        _SESSION_FLAGS[str(root)] = {"active_issue_slug": "7", "delete_local_issue_on_gh": True}

        result = _do_unload_active_issue(delete_file=False)

        assert result["unloaded"] is True
        assert result["file_deleted"] is False
        assert f.exists()

    def test_unload_no_active_slug(self, tmp_path, monkeypatch):
        root = tmp_path
        monkeypatch.setattr("extensions.gh_management.gh_implementation.get_workspace_root", lambda: root)
        from extensions.gh_management.gh_implementation import _SESSION_FLAGS, _do_unload_active_issue
        _SESSION_FLAGS[str(root)] = {"delete_local_issue_on_gh": True}

        result = _do_unload_active_issue()

        assert result["unloaded"] is False
        assert "message" in result
