from datetime import date
from pathlib import Path
import pytest
from plugins.github_planner.storage import (
    STATUS_OPEN,
    STATUS_PENDING,
    list_issue_files,
    read_doc_file,
    read_issue_file,
    read_issue_frontmatter,
    resolve_slug,
    update_issue_status,
    write_doc_file,
    write_issue_file,
)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


# ── write_issue_file ──────────────────────────────────────────────────────────

def test_write_pending_issue_has_status(workspace):
    write_issue_file(
        root=workspace, slug="fix-auth-bug", title="Fix auth bug",
        body="## Overview\nFix it.", assignees=[], labels=[],
        created_at=date(2026, 3, 15),
    )
    fm = read_issue_frontmatter(workspace, "fix-auth-bug")
    assert fm["title"] == "Fix auth bug"
    assert fm["status"] == STATUS_PENDING
    assert fm["created_at"] == "2026-03-15"
    assert "issue_number" not in fm
    assert "github_url" not in fm


def test_write_open_issue_includes_number_and_url(workspace):
    write_issue_file(
        root=workspace, slug="open-issue", title="Open issue",
        body="body", assignees=[], labels=[],
        created_at=date(2026, 3, 15),
        status=STATUS_OPEN,
        issue_number=42,
        github_url="https://github.com/o/r/issues/42",
    )
    fm = read_issue_frontmatter(workspace, "open-issue")
    assert fm["status"] == STATUS_OPEN
    assert fm["issue_number"] == 42
    assert fm["github_url"] == "https://github.com/o/r/issues/42"


def test_read_issue_file_returns_full_content(workspace):
    write_issue_file(
        root=workspace, slug="my-issue", title="My issue",
        body="body text", assignees=[], labels=[], created_at=date(2026, 3, 15),
    )
    content = read_issue_file(workspace, "my-issue")
    assert "My issue" in content
    assert "body text" in content


def test_read_issue_file_returns_none_when_missing(workspace):
    assert read_issue_file(workspace, "no-such-slug") is None


# ── update_issue_status ───────────────────────────────────────────────────────

def test_update_issue_status_to_open(workspace):
    write_issue_file(
        root=workspace, slug="pending-issue", title="Pending",
        body="body", assignees=[], labels=[], created_at=date(2026, 3, 15),
    )
    update_issue_status(workspace, "pending-issue", STATUS_OPEN, issue_number=7, github_url="https://gh/7")
    fm = read_issue_frontmatter(workspace, "pending-issue")
    assert fm["status"] == STATUS_OPEN
    assert fm["issue_number"] == 7
    assert fm["github_url"] == "https://gh/7"


def test_update_issue_status_preserves_body(workspace):
    write_issue_file(
        root=workspace, slug="body-issue", title="Body issue",
        body="important body text", assignees=[], labels=[], created_at=date(2026, 3, 15),
    )
    update_issue_status(workspace, "body-issue", STATUS_OPEN)
    content = read_issue_file(workspace, "body-issue")
    assert "important body text" in content


def test_update_issue_status_returns_none_when_missing(workspace):
    assert update_issue_status(workspace, "nonexistent", STATUS_OPEN) is None


# ── list_issue_files ──────────────────────────────────────────────────────────

def test_list_issue_files_sorted_by_date_desc(workspace):
    for slug, day in [("issue-a", 10), ("issue-b", 15), ("issue-c", 5)]:
        write_issue_file(
            root=workspace, slug=slug, title=slug,
            body="body", assignees=[], labels=[],
            created_at=date(2026, 3, day),
        )
    issues = list_issue_files(workspace)
    assert [i["slug"] for i in issues] == ["issue-b", "issue-a", "issue-c"]


def test_list_issue_files_empty(workspace):
    assert list_issue_files(workspace) == []


def test_list_issue_files_includes_status(workspace):
    write_issue_file(
        root=workspace, slug="full-issue", title="Full issue",
        body="b", assignees=["alice"], labels=["bug"],
        created_at=date(2026, 3, 15),
    )
    issues = list_issue_files(workspace)
    assert issues[0]["status"] == STATUS_PENDING
    assert issues[0]["assignees"] == ["alice"]
    assert issues[0]["labels"] == ["bug"]
    assert issues[0]["issue_number"] is None


# ── doc files ─────────────────────────────────────────────────────────────────

def test_write_and_read_doc_file(workspace):
    write_doc_file(workspace, "project_description", "# My Project\n")
    assert read_doc_file(workspace, "project_description") == "# My Project\n"


def test_write_and_read_architecture_doc(workspace):
    write_doc_file(workspace, "architecture", "# Architecture\n")
    assert read_doc_file(workspace, "architecture") == "# Architecture\n"


def test_read_doc_file_returns_none_when_missing(workspace):
    assert read_doc_file(workspace, "project_description") is None


# ── resolve_slug ──────────────────────────────────────────────────────────────

def test_resolve_slug_no_collision(workspace):
    assert resolve_slug(workspace, "new-issue") == "new-issue"


def test_resolve_slug_collision_increments(workspace):
    (workspace / "hub_agents" / "issues" / "fix-bug.md").write_text("x")
    assert resolve_slug(workspace, "fix-bug") == "fix-bug-2"


def test_resolve_slug_multiple_collisions(workspace):
    issues = workspace / "hub_agents" / "issues"
    (issues / "fix-bug.md").write_text("x")
    (issues / "fix-bug-2.md").write_text("x")
    assert resolve_slug(workspace, "fix-bug") == "fix-bug-3"


# ── read_issue_frontmatter edge cases ─────────────────────────────────────────

def test_read_issue_frontmatter_returns_none_when_missing(workspace):
    assert read_issue_frontmatter(workspace, "no-such-slug") is None


def test_read_issue_frontmatter_returns_none_when_no_frontmatter(workspace):
    path = workspace / "hub_agents" / "issues" / "plain.md"
    path.write_text("# Just a heading\nNo front matter here.")
    assert read_issue_frontmatter(workspace, "plain") is None
