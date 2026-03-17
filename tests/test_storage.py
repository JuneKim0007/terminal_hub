from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
from extensions.github_planner.storage import (
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


# ── _atomic_write exception cleanup ───────────────────────────────────────────

def test_atomic_write_cleans_up_tmp_on_error(tmp_path):
    """Lines 54-59: when the write raises, temp file is removed and exception is re-raised."""
    import os
    from extensions.github_planner.storage import _atomic_write
    target = tmp_path / "output.md"
    # Patch os.replace to blow up after the temp file is written
    original_replace = os.replace
    calls = []
    def bad_replace(src, dst):
        calls.append(src)
        raise OSError("replace failed")
    with patch("extensions.github_planner.storage.os.replace", side_effect=bad_replace):
        with pytest.raises(OSError, match="replace failed"):
            _atomic_write(target, "content")
    # After the exception, no stray .tmp files should remain
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Expected no .tmp files but found: {tmp_files}"


# ── write_issue_file OSError path ──────────────────────────────────────────────

def test_write_issue_file_raises_on_oserror(tmp_path):
    """Lines 54-59: OSError from _atomic_write propagates out of write_issue_file."""
    import os
    from extensions.github_planner.storage import _atomic_write
    issues_dir = tmp_path / "hub_agents" / "issues"
    issues_dir.mkdir(parents=True)
    with patch("extensions.github_planner.storage.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            write_issue_file(
                root=tmp_path, slug="my-issue", title="My Issue",
                body="body", assignees=[], labels=[],
                created_at=date(2026, 3, 15),
            )


# ── read_issue_frontmatter: no YAML separator ─────────────────────────────────

def test_read_issue_frontmatter_no_separator_returns_none(workspace):
    """Line 124: file exists but does not start with '---' → returns None."""
    path = workspace / "hub_agents" / "issues" / "no-sep.md"
    path.write_text("title: something\nbut no separator\n")
    assert read_issue_frontmatter(workspace, "no-sep") is None


# ── write_doc_file / read_doc_file ─────────────────────────────────────────────

def test_write_doc_file_project_description(workspace):
    """Lines 147-148: write_doc_file works for 'project_description'."""
    path = write_doc_file(workspace, "project_description", "# My Project\n")
    assert path.exists()
    assert path.read_text() == "# My Project\n"


def test_write_doc_file_architecture(workspace):
    """Lines 154-155: write_doc_file works for 'architecture'."""
    path = write_doc_file(workspace, "architecture", "## Arch\n")
    assert path.exists()
    assert path.read_text() == "## Arch\n"


def test_read_doc_file_missing_returns_none(workspace):
    """Lines 166-167: path does not exist → returns None."""
    assert read_doc_file(workspace, "architecture") is None


# ── list_issue_files: empty dir and missing dir ───────────────────────────────

def test_list_issue_files_returns_empty_when_dir_missing(tmp_path):
    """Line 174: issues dir doesn't exist → return []."""
    # tmp_path has no hub_agents/issues subdirectory
    result = list_issue_files(tmp_path)
    assert result == []


def test_list_issue_files_ignores_files_with_invalid_slugs(workspace):
    """Lines 180-181: .md files whose stem isn't a valid slug are skipped."""
    bad_file = workspace / "hub_agents" / "issues" / "INVALID SLUG.md"
    bad_file.write_text("---\ntitle: bad\n---\nbody")
    # Should not raise and should return empty list (no valid issues)
    result = list_issue_files(workspace)
    assert all(item["slug"] != "INVALID SLUG" for item in result)


# ── update_issue_status: writes number and url back ──────────────────────────

def test_update_issue_status_writes_number_and_url(workspace):
    """Lines 201, 211, 217-218: update_issue_status persists issue_number and github_url."""
    write_issue_file(
        root=workspace, slug="pending-update", title="Pending",
        body="body text", assignees=[], labels=[],
        created_at=date(2026, 3, 15),
    )
    result = update_issue_status(
        workspace, "pending-update",
        status=STATUS_OPEN,
        issue_number=42,
        github_url="https://github.com/o/r/issues/42",
    )
    assert result is not None
    fm = read_issue_frontmatter(workspace, "pending-update")
    assert fm["status"] == STATUS_OPEN
    assert fm["issue_number"] == 42
    assert fm["github_url"] == "https://github.com/o/r/issues/42"


def test_update_issue_status_without_yaml_separator_returns_none(workspace):
    """Line 124 in update_issue_status: file not starting with '---' → returns None."""
    path = workspace / "hub_agents" / "issues" / "no-fm.md"
    path.write_text("just plain text, no frontmatter")
    result = update_issue_status(workspace, "no-fm", STATUS_OPEN)
    assert result is None


# ── _atomic_write: OSError during unlink (lines 57-58) ────────────────────────

def test_atomic_write_unlink_oserror_is_suppressed_and_exception_still_raises(tmp_path):
    """Lines 57-58: if os.unlink also raises OSError during cleanup, it is silenced
    but the original exception is still re-raised."""
    import os
    from extensions.github_planner.storage import _atomic_write

    def bad_replace(src, dst):
        raise OSError("replace failed")

    def bad_unlink(path):
        raise OSError("unlink also failed")

    with patch("extensions.github_planner.storage.os.replace", side_effect=bad_replace), \
         patch("extensions.github_planner.storage.os.unlink", side_effect=bad_unlink):
        with pytest.raises(OSError, match="replace failed"):
            _atomic_write(tmp_path / "out.md", "content")


# ── read_issue_frontmatter: OSError on read_text (lines 147-148) ──────────────

def test_read_issue_frontmatter_oserror_on_read_returns_none(workspace):
    """Lines 147-148: path.read_text raises OSError → returns None."""
    path = workspace / "hub_agents" / "issues" / "my-issue.md"
    path.write_text("---\ntitle: test\n---\nbody")
    with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
        result = read_issue_frontmatter(workspace, "my-issue")
    assert result is None


# ── read_issue_frontmatter: YAMLError (lines 154-155) ─────────────────────────

def test_read_issue_frontmatter_yaml_error_returns_none(workspace):
    """Lines 154-155: yaml.safe_load raises YAMLError → returns None."""
    import yaml
    path = workspace / "hub_agents" / "issues" / "bad-yaml.md"
    # Write something that starts with --- but has invalid YAML in the front matter block
    path.write_text("---\n{invalid: yaml: :\n---\nbody")
    # Patch yaml.safe_load to force a YAMLError
    with patch("extensions.github_planner.storage.yaml.safe_load", side_effect=yaml.YAMLError("bad")):
        result = read_issue_frontmatter(workspace, "bad-yaml")
    assert result is None


# ── read_issue_file: OSError on read_text (lines 166-167) ─────────────────────

def test_read_issue_file_oserror_on_read_returns_none(workspace):
    """Lines 166-167: path.read_text raises OSError → returns None."""
    path = workspace / "hub_agents" / "issues" / "my-issue.md"
    path.write_text("content")
    with patch("pathlib.Path.read_text", side_effect=OSError("io error")):
        result = read_issue_file(workspace, "my-issue")
    assert result is None


# ── write_doc_file: invalid doc_key raises ValueError (line 201) ──────────────

def test_write_doc_file_invalid_key_raises_value_error(workspace):
    """Line 201: unknown doc_key raises ValueError."""
    with pytest.raises(ValueError, match="Unknown doc_key"):
        write_doc_file(workspace, "nonexistent_doc", "content")


# ── read_doc_file: OSError on read_text (lines 217-218) ──────────────────────

def test_read_doc_file_oserror_on_read_returns_none(workspace):
    """Lines 217-218: path exists but read_text raises OSError → returns None."""
    doc_path = workspace / "hub_agents" / "project_description.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("content")
    with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
        result = read_doc_file(workspace, "project_description")
    assert result is None
