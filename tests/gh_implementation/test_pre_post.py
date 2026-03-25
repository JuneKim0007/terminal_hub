"""Tests for pre_implementation and post_implementation."""
from unittest.mock import MagicMock, patch
from pathlib import Path


def test_pre_implementation_returns_context(tmp_path):
    from extensions.gh_management.gh_implementation import _do_pre_implementation

    ctx = {
        "workspace_ready": True, "repo_confirmed": "owner/repo",
        "project_summary": "summary", "issue_content": {"slug": "42", "agent_workflow": ["step1"]},
        "design_sections": {}, "has_agent_workflow": True, "context_ready": True,
    }
    with patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.gh_implementation._load_persistent_flags"), \
         patch("extensions.gh_management.gh_implementation._get_flags",
               return_value={"lookup_design_refs": True, "run_verify": True, "run_make_test": True,
                             "close_automatically_on_gh": True, "delete_local_issue_on_gh": True,
                             "sync_docs_on_close": True, "auto_switch_modes": False}), \
         patch("extensions.gh_management.github_planner._do_apply_unload_policy",
               return_value={"cleared": []}), \
         patch("extensions.gh_management.github_planner.workspace_tools._do_load_implementation_context",
               return_value=ctx):
        result = _do_pre_implementation("42")

    assert result["workspace_ready"] is True
    assert result["has_agent_workflow"] is True
    assert result["active_issue"]["slug"] == "42"
    assert "Context loaded" in result["_display"]


def test_pre_implementation_error_propagates(tmp_path):
    from extensions.gh_management.gh_implementation import _do_pre_implementation

    with patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.gh_implementation._load_persistent_flags"), \
         patch("extensions.gh_management.gh_implementation._get_flags",
               return_value={"lookup_design_refs": True}), \
         patch("extensions.gh_management.github_planner._do_apply_unload_policy",
               return_value={"cleared": []}), \
         patch("extensions.gh_management.github_planner.workspace_tools._do_load_implementation_context",
               return_value={"error": "issue_not_found", "message": "No issue"}):
        result = _do_pre_implementation("999")

    assert "error" in result


def test_post_implementation_returns_diff_and_tests(tmp_path):
    from extensions.gh_management.gh_implementation import _do_post_implementation

    test_result = {
        "passed": True, "failed": 0, "coverage": 92.0,
        "meets_threshold": True, "filtered_output": "All good",
    }

    with patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.gh_implementation._load_persistent_flags"), \
         patch("extensions.gh_management.gh_implementation._get_flags",
               return_value={"run_verify": True, "run_make_test": True,
                             "close_automatically_on_gh": True, "sync_docs_on_close": False}), \
         patch("extensions.gh_management.gh_implementation._do_run_tests_filtered",
               return_value=test_result), \
         patch("subprocess.run") as mock_run:
        # Only one call: git diff HEAD (git diff --name-only HEAD is skipped because affected_files is provided)
        mock_run.return_value = MagicMock(stdout="diff --git a/foo.py b/foo.py\n+new line\n", returncode=0)
        result = _do_post_implementation("42", affected_files=["terminal_hub/foo.py"])

    assert result["affected_files"] == ["terminal_hub/foo.py"]
    assert result["test_results"]["passed"] is True
    assert result["diff"]["files_changed"] == 1
    assert "Tests:" in result["_display"]


def test_post_implementation_skips_tests_when_no_files(tmp_path):
    from extensions.gh_management.gh_implementation import _do_post_implementation

    with patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=tmp_path), \
         patch("extensions.gh_management.gh_implementation._load_persistent_flags"), \
         patch("extensions.gh_management.gh_implementation._get_flags",
               return_value={"run_verify": True}), \
         patch("extensions.gh_management.gh_implementation._do_run_tests_filtered") as mock_tests, \
         patch("subprocess.run",
               return_value=MagicMock(stdout="diff --git a/x b/x\n", returncode=0)):
        result = _do_post_implementation("42", affected_files=[])

    mock_tests.assert_not_called()
    assert result["test_results"] == {}


def test_load_persistent_flags_from_config(tmp_path):
    from extensions.gh_management.gh_implementation import _load_persistent_flags, _SESSION_FLAGS

    _SESSION_FLAGS.clear()
    config_dir = tmp_path / "hub_agents"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "gh_implementation:\n  run_verify: false\n  close_automatically_on_gh: false\n"
    )

    with patch("extensions.gh_management.gh_implementation.get_workspace_root", return_value=tmp_path):
        _load_persistent_flags(tmp_path)

    flags = _SESSION_FLAGS[str(tmp_path)]
    assert flags["run_verify"] is False
    assert flags["close_automatically_on_gh"] is False
    _SESSION_FLAGS.clear()
