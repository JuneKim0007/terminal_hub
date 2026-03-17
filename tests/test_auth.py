import subprocess
from unittest.mock import patch
import pytest
from plugins.github_planner.auth import resolve_token, TokenSource, get_auth_options


def test_returns_env_token_first():
    with patch.dict("os.environ", {"GITHUB_TOKEN": "env-token"}):
        token, source = resolve_token()
    assert token == "env-token"
    assert source == TokenSource.ENV


def test_falls_back_to_gh_cli():
    with patch.dict("os.environ", {}, clear=True), \
         patch("subprocess.check_output", return_value=b"gh-token-abc\n"):
        token, source = resolve_token()
    assert token == "gh-token-abc"
    assert source == TokenSource.GH_CLI


def test_returns_none_when_both_missing():
    with patch.dict("os.environ", {}, clear=True), \
         patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "gh")):
        token, source = resolve_token()
    assert token is None
    assert source == TokenSource.NONE


def test_gh_cli_not_installed_returns_none():
    with patch.dict("os.environ", {}, clear=True), \
         patch("subprocess.check_output", side_effect=FileNotFoundError):
        token, source = resolve_token()
    assert token is None
    assert source == TokenSource.NONE


def test_token_source_suggestion_env():
    assert TokenSource.ENV.suggestion() == ""


def test_token_source_suggestion_gh_cli():
    assert TokenSource.GH_CLI.suggestion() == ""


def test_get_auth_options_returns_two_choices():
    options = get_auth_options()
    assert len(options) == 2
    assert options[0]["value"] == "gh_cli"
    assert options[1]["value"] == "token"
    assert "gh auth login" in options[0]["instructions"]
    assert "GITHUB_TOKEN" in options[1]["instructions"]


def test_get_auth_options_include_verify_hint():
    options = get_auth_options()
    # gh_cli option should tell Claude to call verify_auth after user runs the command
    assert "verify_auth" in options[0]["next_step"]


def test_token_source_suggestion_none():
    msg = TokenSource.NONE.suggestion()
    assert "check_auth" in msg
    assert len(msg) > 0


# ── verify_gh_cli_auth ────────────────────────────────────────────────────────

from plugins.github_planner.auth import verify_gh_cli_auth


def test_verify_gh_cli_auth_success():
    with patch("subprocess.check_output", return_value=b"some-token\n"):
        success, message = verify_gh_cli_auth()
    assert success is True
    assert "verified" in message.lower()


def test_verify_gh_cli_auth_empty_token():
    with patch("subprocess.check_output", return_value=b""):
        success, message = verify_gh_cli_auth()
    assert success is False
    assert "gh auth login" in message


def test_verify_gh_cli_auth_not_installed():
    with patch("subprocess.check_output", side_effect=FileNotFoundError):
        success, message = verify_gh_cli_auth()
    assert success is False
    assert "not installed" in message.lower()


def test_verify_gh_cli_auth_not_authenticated():
    with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "gh")):
        success, message = verify_gh_cli_auth()
    assert success is False
    assert "gh auth login" in message
