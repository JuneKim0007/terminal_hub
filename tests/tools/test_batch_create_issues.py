"""Tests for batch_create_issues — drafts N issues, optionally submits them all."""
from unittest.mock import patch

import pytest

from extensions.gh_management.github_planner.issues import _do_batch_create_issues


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def batch(workspace):
    """Run the tool with a known label set and a stubbed submit."""
    def run(specs, confirm_before_submit=True, submit_result=None):
        submit = submit_result or (lambda slug: {"issue_number": 7, "url": "https://gh/7"})
        with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.gh_management.github_planner.labels._do_list_repo_labels",
                   return_value={"labels": [{"name": "bug"}, {"name": "enhancement"}]}), \
             patch("extensions.gh_management.github_planner.issues._do_submit_issue",
                   side_effect=submit):
            return _do_batch_create_issues(specs, confirm_before_submit=confirm_before_submit)
    return run


def test_drafts_every_spec_without_submitting_by_default(batch, workspace):
    """confirm_before_submit=True drafts locally and stops — nothing reaches GitHub."""
    result = batch([
        {"title": "Fix login", "body": "b", "labels": ["bug"]},
        {"title": "Add search", "body": "b", "labels": ["enhancement"]},
    ])

    assert [d["title"] for d in result["drafts"]] == ["Fix login", "Add search"]
    assert result["submitted"] == []
    assert result["all_succeeded"] is False, "nothing was submitted, so nothing succeeded"
    assert "About to create 2 GitHub issues" in result["confirmation_display"]
    assert len(list((workspace / "hub_agents" / "issues").glob("*.md"))) == 2


def test_reports_unknown_labels_without_blocking_the_draft(batch):
    """An unknown label is a warning, not a failure — the draft is still written."""
    result = batch([{"title": "Fix login", "body": "b", "labels": ["bug", "nonsense"]}])

    assert result["validation_errors"] == ["Unknown labels for 'Fix login': ['nonsense']"]
    assert len(result["drafts"]) == 1
    assert "1 validation warning(s)" in result["_display"]


def test_submits_every_draft_when_confirmation_is_waived(batch):
    result = batch(
        [{"title": "Fix login", "body": "b"}, {"title": "Add search", "body": "b"}],
        confirm_before_submit=False,
    )

    assert len(result["submitted"]) == 2
    assert result["submitted"][0]["issue_number"] == 7
    assert result["all_succeeded"] is True


def test_a_failed_submission_is_reported_and_does_not_stop_the_rest(batch):
    calls = {"n": 0}

    def flaky(slug):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"error": "github_error"}
        return {"issue_number": 9, "url": "https://gh/9"}

    result = batch(
        [{"title": "First", "body": "b"}, {"title": "Second", "body": "b"}],
        confirm_before_submit=False,
        submit_result=flaky,
    )

    assert len(result["failed_submissions"]) == 1
    assert result["failed_submissions"][0]["error"] == "github_error"
    assert len(result["submitted"]) == 1, "the second issue still went out"
    assert result["all_succeeded"] is False
