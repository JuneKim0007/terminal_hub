import subprocess
from unittest.mock import patch
import pytest
from terminal_hub.auth import resolve_token, TokenSource, get_auth_options


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
