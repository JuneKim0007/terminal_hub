"""Tests for extensions.gh_management.github_planner.analyzer — pure functions and I/O helpers."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from extensions.gh_management.github_planner.analyzer import (
    extract_label_patterns, extract_assignee_patterns, extract_body_structure,
    extract_title_prefixes, process_snapshot, load_snapshot, write_snapshot,
    snapshot_age_hours, summarize_for_prompt, _strip_code_blocks,
)

ISSUES = [
    {"title": "Fix auth bug", "body": "## Description\nFix it.", "state": "open",
     "labels": [{"name": "bug"}], "assignees": [{"login": "alice"}]},
    {"title": "Fix login", "body": "## Description\n## Acceptance Criteria\nAC here.", "state": "closed",
     "labels": [{"name": "bug"}, {"name": "feature"}], "assignees": [{"login": "bob"}]},
    {"title": "Add feature", "body": "## Acceptance Criteria\nNew feature.", "state": "open",
     "labels": [{"name": "feature"}], "assignees": [{"login": "alice"}]},
]

def test_extract_label_patterns_frequency():
    result = extract_label_patterns(ISSUES)
    assert result["frequency"]["bug"] == 2
    assert result["frequency"]["feature"] == 2

def test_extract_label_patterns_suggested_ordered():
    result = extract_label_patterns(ISSUES)
    assert "bug" in result["suggested"]
    assert "feature" in result["suggested"]

def test_extract_label_patterns_empty():
    result = extract_label_patterns([])
    assert result == {"frequency": {}, "suggested": []}

def test_extract_label_patterns_string_labels():
    issues = [{"labels": ["bug", "feature"], "assignees": []}]
    result = extract_label_patterns(issues)
    assert result["frequency"]["bug"] == 1
    assert result["frequency"]["feature"] == 1

def test_extract_assignee_patterns():
    result = extract_assignee_patterns(ISSUES)
    assert result["frequency"]["alice"] == 2
    assert result["frequency"]["bob"] == 1
    assert result["suggested"][0] == "alice"

def test_extract_assignee_patterns_empty():
    result = extract_assignee_patterns([])
    assert result == {"frequency": {}, "suggested": []}

def test_extract_assignee_patterns_string_assignees():
    issues = [{"assignees": ["alice", "bob"], "labels": []}]
    result = extract_assignee_patterns(issues)
    assert result["frequency"]["alice"] == 1
    assert result["frequency"]["bob"] == 1

def test_strip_code_blocks():
    text = "before\n```python\ndef foo(): pass\n```\nafter"
    assert "def foo" not in _strip_code_blocks(text)
    assert "after" in _strip_code_blocks(text)

def test_strip_code_blocks_no_code():
    text = "no code here"
    assert _strip_code_blocks(text) == text

def test_extract_body_structure_ratio():
    result = extract_body_structure(ISSUES)
    # "## Description" appears in 2 of 3 issues
    assert "## Description" in result
    assert abs(result["## Description"] - 0.67) < 0.01

def test_extract_body_structure_strips_code_blocks():
    issues = [{"body": "```\n## Fake heading\n```\n## Real heading"}]
    result = extract_body_structure(issues)
    assert "## Fake heading" not in result
    assert "## Real heading" in result

def test_extract_body_structure_empty():
    assert extract_body_structure([]) == {}

def test_extract_body_structure_none_body():
    issues = [{"body": None}, {"body": "## Section\nContent"}]
    result = extract_body_structure(issues)
    assert "## Section" in result

def test_extract_body_structure_no_duplicates_per_issue():
    issues = [{"body": "## Section\nContent\n## Section\nMore"}]
    result = extract_body_structure(issues)
    # "## Section" should only be counted once per issue
    assert result["## Section"] == 1.0

def test_extract_title_prefixes():
    result = extract_title_prefixes(ISSUES)
    assert "Fix" in result
    assert len(result) <= 5

def test_extract_title_prefixes_empty():
    result = extract_title_prefixes([])
    assert result == []

def test_extract_title_prefixes_empty_title():
    result = extract_title_prefixes([{"title": ""}, {"title": "Fix this"}])
    assert "Fix" in result

def test_process_snapshot_structure():
    snap = process_snapshot(ISSUES, [{"name": "bug", "color": "red", "description": ""}],
                            [{"login": "alice"}], repo="owner/repo")
    assert snap["repo"] == "owner/repo"
    assert snap["issues"]["total_sampled"] == 3
    assert snap["issues"]["total_open"] == 2
    assert "templates" in snap
    assert "analyzed_at" in snap

def test_process_snapshot_empty_repo():
    snap = process_snapshot([], [], [], repo="owner/repo")
    assert snap["issues"]["total_sampled"] == 0
    assert snap["issues"]["avg_body_length"] == 0

def test_process_snapshot_label_info():
    snap = process_snapshot(ISSUES, [{"name": "bug", "color": "red", "description": "a bug"}],
                            [], repo="r")
    label = next(l for l in snap["labels"] if l["name"] == "bug")
    assert label["color"] == "red"
    assert label["description"] == "a bug"

def test_process_snapshot_member_issue_count():
    snap = process_snapshot(ISSUES, [], [{"login": "alice"}, {"login": "bob"}], repo="r")
    alice = next(m for m in snap["members"] if m["login"] == "alice")
    assert alice["issues_assigned"] == 2

def test_process_snapshot_templates():
    snap = process_snapshot(ISSUES, [], [], repo="r")
    assert "suggested_labels" in snap["templates"]
    assert "suggested_assignees" in snap["templates"]
    assert "most_common_sections" in snap["templates"]

def test_write_and_load_snapshot(tmp_path):
    (tmp_path / "hub_agents").mkdir()
    snap = {"analyzed_at": "2026-01-01T00:00:00+00:00", "repo": "r"}
    write_snapshot(tmp_path, snap)
    loaded = load_snapshot(tmp_path)
    assert loaded["repo"] == "r"

def test_write_snapshot_creates_dir(tmp_path):
    snap = {"analyzed_at": "2026-01-01T00:00:00+00:00", "repo": "r"}
    path = write_snapshot(tmp_path, snap)
    assert path.exists()

def test_load_snapshot_missing(tmp_path):
    assert load_snapshot(tmp_path) is None

def test_load_snapshot_corrupt(tmp_path):
    (tmp_path / "hub_agents").mkdir()
    (tmp_path / "hub_agents" / "analyzer_snapshot.json").write_text("not json")
    assert load_snapshot(tmp_path) is None

def test_snapshot_age_hours_recent():
    snap = {"analyzed_at": datetime.now(timezone.utc).isoformat()}
    assert snapshot_age_hours(snap) < 0.01

def test_snapshot_age_hours_old():
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    snap = {"analyzed_at": old.isoformat()}
    assert snapshot_age_hours(snap) > 24

def test_snapshot_age_hours_missing_field():
    assert snapshot_age_hours({}) == float("inf")

def test_snapshot_age_hours_invalid_value():
    assert snapshot_age_hours({"analyzed_at": "not-a-date"}) == float("inf")

def test_summarize_for_prompt_populated():
    snap = process_snapshot(ISSUES, [{"name": "bug", "color": "", "description": ""}],
                            [{"login": "alice"}], repo="r")
    result = summarize_for_prompt(snap)
    assert result.startswith("[analyzer]")
    assert len(result) < 300

def test_summarize_for_prompt_none():
    assert summarize_for_prompt(None) == ""

def test_summarize_for_prompt_empty_dict():
    assert summarize_for_prompt({}) == ""

def test_summarize_for_prompt_no_data():
    snap = {"issues": {"label_frequency": {}, "assignee_frequency": {},
                       "body_sections": {}, "title_prefixes": []},
            "templates": {"suggested_assignees": []}}
    result = summarize_for_prompt(snap)
    assert result == ""

def test_summarize_for_prompt_partial_data():
    snap = {"issues": {"label_frequency": {"bug": 2}, "body_sections": {}, "title_prefixes": []},
            "templates": {"suggested_assignees": []}}
    result = summarize_for_prompt(snap)
    assert "[analyzer]" in result
    assert "bug" in result


def test_summarize_for_prompt_exception_returns_empty():
    """summarize_for_prompt returns '' when an exception is raised (lines 185-186)."""
    import extensions.gh_management.github_planner.analyzer as ana
    # Pass a snap that makes the function crash at repr/str step
    bad_snap = MagicMock()
    bad_snap.__bool__ = MagicMock(side_effect=RuntimeError("boom"))
    # The function starts with `if not snap: return ""` — force it past that
    # by passing a malformed dict that raises during processing
    class BadDict(dict):
        def get(self, key, default=None):
            raise RuntimeError("boom during get")
    result = summarize_for_prompt(BadDict({"x": 1}))
    assert result == ""
