from datetime import date
from pathlib import Path
import pytest
from terminal_hub.storage import (
    write_issue_file,
    read_issue_frontmatter,
    read_issue_file,
    list_issue_files,
    write_doc_file,
    read_doc_file,
    resolve_slug,
)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def test_write_and_read_issue(workspace):
    write_issue_file(
        root=workspace, slug="fix-auth-bug", title="Fix auth bug",
        issue_number=42, github_url="https://github.com/o/r/issues/42",
        body="## Overview\nFix it.", assignees=[], labels=[],
        created_at=date(2026, 3, 15),
    )
    fm = read_issue_frontmatter(workspace, "fix-auth-bug")
    assert fm["title"] == "Fix auth bug"
    assert fm["issue_number"] == 42
    assert fm["github_url"] == "https://github.com/o/r/issues/42"
    assert fm["created_at"] == "2026-03-15"
    assert fm["assignees"] == []
    assert fm["labels"] == []


def test_read_issue_file_returns_full_content(workspace):
    write_issue_file(
        root=workspace, slug="my-issue", title="My issue", issue_number=1,
        github_url="https://github.com/o/r/issues/1", body="body text",
        assignees=[], labels=[], created_at=date(2026, 3, 15),
    )
    content = read_issue_file(workspace, "my-issue")
    assert "My issue" in content
    assert "body text" in content


def test_read_issue_file_returns_none_when_missing(workspace):
    assert read_issue_file(workspace, "no-such-slug") is None


def test_list_issue_files_sorted_by_date_desc(workspace):
    for slug, day in [("issue-a", 10), ("issue-b", 15), ("issue-c", 5)]:
        write_issue_file(
            root=workspace, slug=slug, title=slug, issue_number=1,
            github_url="https://github.com/o/r/issues/1",
            body="body", assignees=[], labels=[],
            created_at=date(2026, 3, day),
        )
    issues = list_issue_files(workspace)
    assert [i["slug"] for i in issues] == ["issue-b", "issue-a", "issue-c"]


def test_list_issue_files_empty(workspace):
    assert list_issue_files(workspace) == []


def test_list_issue_files_includes_all_fields(workspace):
    write_issue_file(
        root=workspace, slug="full-issue", title="Full issue", issue_number=7,
        github_url="https://github.com/o/r/issues/7", body="b",
        assignees=["alice"], labels=["bug"], created_at=date(2026, 3, 15),
    )
    issues = list_issue_files(workspace)
    assert issues[0]["assignees"] == ["alice"]
    assert issues[0]["labels"] == ["bug"]
    assert issues[0]["issue_number"] == 7


def test_write_and_read_doc_file(workspace):
    write_doc_file(workspace, "project_description", "# My Project\n")
    assert read_doc_file(workspace, "project_description") == "# My Project\n"


def test_write_and_read_architecture_doc(workspace):
    write_doc_file(workspace, "architecture", "# Architecture\n")
    assert read_doc_file(workspace, "architecture") == "# Architecture\n"


def test_read_doc_file_returns_none_when_missing(workspace):
    assert read_doc_file(workspace, "project_description") is None


def test_resolve_slug_no_collision(workspace):
    assert resolve_slug(workspace, "new-issue") == "new-issue"


def test_resolve_slug_collision_increments(workspace):
    (workspace / "hub_agents" / "issues" / "fix-bug.md").write_text("x")
    assert resolve_slug(workspace, "fix-bug") == "fix-bug-2"


def test_read_issue_frontmatter_returns_none_when_missing(workspace):
    assert read_issue_frontmatter(workspace, "no-such-slug") is None


def test_read_issue_frontmatter_returns_none_when_no_frontmatter(workspace):
    path = workspace / "hub_agents" / "issues" / "plain.md"
    path.write_text("# Just a heading\nNo front matter here.")
    assert read_issue_frontmatter(workspace, "plain") is None


def test_resolve_slug_multiple_collisions(workspace):
    issues = workspace / "hub_agents" / "issues"
    (issues / "fix-bug.md").write_text("x")
    (issues / "fix-bug-2.md").write_text("x")
    assert resolve_slug(workspace, "fix-bug") == "fix-bug-3"
