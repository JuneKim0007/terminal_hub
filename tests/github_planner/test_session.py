"""Tests for github_planner.session — repo confirmation and auth wrappers."""
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clear_session_cache():
    from extensions.gh_management.github_planner.session import _SESSION_REPO_CONFIRMED
    _SESSION_REPO_CONFIRMED.clear()
    yield
    _SESSION_REPO_CONFIRMED.clear()


def _make_pkg(root, repo="owner/myrepo", token="tok"):
    pkg = MagicMock()
    pkg.get_workspace_root.return_value = root
    pkg.read_env.return_value = {"GITHUB_REPO": repo}
    pkg.resolve_token.return_value = (token, MagicMock(value="env_var", suggestion=lambda: ""))
    pkg.verify_gh_cli_auth.return_value = (True, "Authenticated")
    return pkg


# ── _do_confirm_session_repo ──────────────────────────────────────────────────

def test_confirm_no_repo_configured(tmp_path):
    from extensions.gh_management.github_planner.session import _do_confirm_session_repo
    pkg = MagicMock()
    pkg.get_workspace_root.return_value = tmp_path
    pkg.read_env.return_value = {"GITHUB_REPO": ""}
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg):
        result = _do_confirm_session_repo()
    assert result["confirmed"] is False
    assert result["repo"] is None
    assert "No GITHUB_REPO" in result["_display"]


def test_confirm_not_yet_confirmed_returns_prompt(tmp_path):
    from extensions.gh_management.github_planner.session import _do_confirm_session_repo
    pkg = _make_pkg(tmp_path)
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg), \
         patch("extensions.gh_management.github_planner.session._detect_project_name", return_value=None):
        result = _do_confirm_session_repo()
    assert result["confirmed"] is False
    assert result["repo"] == "owner/myrepo"
    assert "Working repo" in result["_display"]


def test_confirm_already_confirmed_returns_true(tmp_path):
    from extensions.gh_management.github_planner.session import _do_confirm_session_repo, _SESSION_REPO_CONFIRMED
    _SESSION_REPO_CONFIRMED[str(tmp_path)] = "owner/myrepo"
    pkg = _make_pkg(tmp_path)
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg):
        result = _do_confirm_session_repo(force=False)
    assert result["confirmed"] is True
    assert result["repo"] == "owner/myrepo"


def test_confirm_force_re_prompts_even_when_confirmed(tmp_path):
    from extensions.gh_management.github_planner.session import _do_confirm_session_repo, _SESSION_REPO_CONFIRMED
    _SESSION_REPO_CONFIRMED[str(tmp_path)] = "owner/myrepo"
    pkg = _make_pkg(tmp_path)
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg), \
         patch("extensions.gh_management.github_planner.session._detect_project_name", return_value=None):
        result = _do_confirm_session_repo(force=True)
    # force=True clears cache and re-prompts
    assert result["confirmed"] is False


def test_confirm_repo_changed_since_confirmation(tmp_path):
    from extensions.gh_management.github_planner.session import _do_confirm_session_repo, _SESSION_REPO_CONFIRMED
    _SESSION_REPO_CONFIRMED[str(tmp_path)] = "owner/oldrepo"
    pkg = _make_pkg(tmp_path, repo="owner/myrepo")  # env changed
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg), \
         patch("extensions.gh_management.github_planner.session._detect_project_name", return_value=None):
        result = _do_confirm_session_repo(force=False)
    # repo changed — should re-prompt
    assert result["confirmed"] is False
    assert result["repo"] == "owner/myrepo"


def test_confirm_shows_match_hint_when_project_name_matches(tmp_path):
    from extensions.gh_management.github_planner.session import _do_confirm_session_repo
    pkg = _make_pkg(tmp_path, repo="owner/myrepo")
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg), \
         patch("extensions.gh_management.github_planner.session._detect_project_name", return_value="myrepo"):
        result = _do_confirm_session_repo()
    assert "matches project name" in result["_display"]


# ── _do_set_session_repo ──────────────────────────────────────────────────────

def test_set_session_repo_locks_session(tmp_path):
    from extensions.gh_management.github_planner.session import _do_set_session_repo, _SESSION_REPO_CONFIRMED
    pkg = MagicMock()
    pkg.get_workspace_root.return_value = tmp_path
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg):
        result = _do_set_session_repo("owner/newrepo")
    assert result["confirmed"] is True
    assert result["repo"] == "owner/newrepo"
    assert _SESSION_REPO_CONFIRMED[str(tmp_path)] == "owner/newrepo"


# ── _do_clear_session_repo ────────────────────────────────────────────────────

def test_clear_session_repo_removes_entry(tmp_path):
    from extensions.gh_management.github_planner.session import _do_clear_session_repo, _SESSION_REPO_CONFIRMED
    _SESSION_REPO_CONFIRMED[str(tmp_path)] = "owner/myrepo"
    pkg = MagicMock()
    pkg.get_workspace_root.return_value = tmp_path
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg):
        result = _do_clear_session_repo()
    assert result["cleared"] is True
    assert str(tmp_path) not in _SESSION_REPO_CONFIRMED


def test_clear_session_repo_not_confirmed(tmp_path):
    from extensions.gh_management.github_planner.session import _do_clear_session_repo
    pkg = MagicMock()
    pkg.get_workspace_root.return_value = tmp_path
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg):
        result = _do_clear_session_repo()
    assert result["cleared"] is False


# ── _do_check_auth ────────────────────────────────────────────────────────────

def test_check_auth_authenticated(tmp_path):
    from extensions.gh_management.github_planner.session import _do_check_auth
    pkg = _make_pkg(tmp_path)
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg):
        result = _do_check_auth()
    assert result["authenticated"] is True
    assert result["source"] == "env_var"


def test_check_auth_not_authenticated(tmp_path):
    from extensions.gh_management.github_planner.session import _do_check_auth
    pkg = MagicMock()
    pkg.resolve_token.return_value = (None, MagicMock(suggestion=lambda: "Set GITHUB_TOKEN"))
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg):
        result = _do_check_auth()
    assert result["authenticated"] is False
    assert "options" in result


# ── _do_verify_auth ───────────────────────────────────────────────────────────

def test_verify_auth_success(tmp_path):
    from extensions.gh_management.github_planner.session import _do_verify_auth
    pkg = MagicMock()
    pkg.verify_gh_cli_auth.return_value = (True, "Logged in as user")
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg):
        result = _do_verify_auth()
    assert result["authenticated"] is True
    assert result["source"] == "gh_cli"


def test_verify_auth_failure(tmp_path):
    from extensions.gh_management.github_planner.session import _do_verify_auth
    pkg = MagicMock()
    pkg.verify_gh_cli_auth.return_value = (False, "Not logged in")
    with patch("extensions.gh_management.github_planner.session._pkg", return_value=pkg):
        result = _do_verify_auth()
    assert result["authenticated"] is False
    assert "options" in result
