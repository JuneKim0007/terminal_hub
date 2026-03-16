"""Tests for tui.py parsing and formatting logic (no curses rendering)."""
from unittest.mock import MagicMock, patch
import pytest
from terminal_hub.tui import (
    format_number, format_labels, format_detail_lines, truncate,
    IssueBrowser, run_browser,
)


# ── truncate ──────────────────────────────────────────────────────────────────

def test_truncate_short_string_unchanged():
    assert truncate("hello", 10) == "hello"

def test_truncate_exact_length_unchanged():
    assert truncate("hello", 5) == "hello"

def test_truncate_long_string_adds_ellipsis():
    assert truncate("hello world", 8) == "hello w…"

def test_truncate_zero_width_returns_empty():
    assert truncate("hello", 0) == ""

def test_truncate_one_width_returns_ellipsis():
    assert truncate("hello", 1) == "…"


# ── format_number ─────────────────────────────────────────────────────────────

def test_format_number_with_issue_number():
    assert format_number({"issue_number": 42}) == "#42"

def test_format_number_without_issue_number():
    assert format_number({}) == "local"

def test_format_number_none_issue_number():
    assert format_number({"issue_number": None}) == "local"


# ── format_labels ─────────────────────────────────────────────────────────────

def test_format_labels_empty_list():
    assert format_labels([]) == ""

def test_format_labels_single():
    assert format_labels(["bug"]) == "[bug]"

def test_format_labels_two():
    assert format_labels(["bug", "urgent"]) == "[bug] [urgent]"

def test_format_labels_three_truncates_to_two():
    result = format_labels(["bug", "urgent", "wontfix"])
    assert result == "[bug] [urgent] +1"

def test_format_labels_many_shows_count():
    result = format_labels(["a", "b", "c", "d"])
    assert result == "[a] [b] +2"


# ── format_detail_lines ───────────────────────────────────────────────────────

def _full_issue(**overrides):
    base = {
        "issue_number": 7,
        "title": "Fix the thing",
        "status": "open",
        "created_at": "2026-03-16",
        "assignees": ["alice", "bob"],
        "labels": ["bug", "urgent"],
        "github_url": "https://github.com/owner/repo/issues/7",
        "file": "hub_agents/issues/fix-the-thing.md",
    }
    base.update(overrides)
    return base


def test_detail_lines_all_fields_present():
    lines = format_detail_lines(_full_issue())
    keys = [k for k, _ in lines]
    assert "Status" in keys
    assert "Created" in keys
    assert "Assignees" in keys
    assert "Labels" in keys
    assert "URL" in keys
    assert "File" in keys


def test_detail_lines_no_assignees_skipped():
    lines = format_detail_lines(_full_issue(assignees=[]))
    keys = [k for k, _ in lines]
    assert "Assignees" not in keys


def test_detail_lines_none_assignees_skipped():
    lines = format_detail_lines(_full_issue(assignees=None))
    keys = [k for k, _ in lines]
    assert "Assignees" not in keys


def test_detail_lines_no_labels_skipped():
    lines = format_detail_lines(_full_issue(labels=[]))
    keys = [k for k, _ in lines]
    assert "Labels" not in keys


def test_detail_lines_no_github_url_skipped():
    lines = format_detail_lines(_full_issue(github_url=None))
    keys = [k for k, _ in lines]
    assert "URL" not in keys


def test_detail_lines_no_created_at_skipped():
    lines = format_detail_lines(_full_issue(created_at=None))
    keys = [k for k, _ in lines]
    assert "Created" not in keys


def test_detail_lines_status_always_present():
    lines = format_detail_lines(_full_issue(status=None))
    keys = [k for k, _ in lines]
    # status with None value is still shown as "—"
    assert "Status" in keys


def test_detail_lines_file_always_present():
    lines = format_detail_lines(_full_issue())
    keys = [k for k, _ in lines]
    assert "File" in keys


def test_detail_lines_assignees_value_joined():
    lines = format_detail_lines(_full_issue(assignees=["alice", "bob"]))
    d = dict(lines)
    assert d["Assignees"] == "alice, bob"


def test_detail_lines_labels_value_formatted():
    lines = format_detail_lines(_full_issue(labels=["bug", "urgent"]))
    d = dict(lines)
    assert d["Labels"] == "bug, urgent"


def test_detail_lines_local_issue_no_url():
    lines = format_detail_lines(_full_issue(github_url=None, issue_number=None))
    keys = [k for k, _ in lines]
    assert "URL" not in keys


# ── IssueBrowser.__init__ ─────────────────────────────────────────────────────

def test_issue_browser_init_stores_issues():
    mock_scr = MagicMock()
    issues = [_full_issue(), _full_issue(issue_number=8, title="Second")]
    browser = IssueBrowser(mock_scr, issues)
    assert browser._issues is issues
    assert browser._cursor == 0
    assert browser._expanded == set()


def test_issue_browser_init_empty_issues():
    mock_scr = MagicMock()
    browser = IssueBrowser(mock_scr, [])
    assert browser._issues == []


# ── run_browser ───────────────────────────────────────────────────────────────

def test_run_browser_no_issues_prints_message(capsys):
    with patch("terminal_hub.tui.list_issue_files", return_value=[]):
        with patch("terminal_hub.tui.resolve_workspace_root", return_value="/fake"):
            run_browser()
    captured = capsys.readouterr()
    assert "No issues found" in captured.out


def test_run_browser_with_issues_calls_curses_wrapper():
    issues = [_full_issue()]
    with patch("terminal_hub.tui.list_issue_files", return_value=issues):
        with patch("terminal_hub.tui.resolve_workspace_root", return_value="/fake"):
            with patch("terminal_hub.tui.curses.wrapper") as mock_wrapper:
                run_browser()
                mock_wrapper.assert_called_once()
