import subprocess
from unittest.mock import patch
import pytest
from terminal_hub.auth import resolve_token, TokenSource


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


def test_token_source_suggestion_none():
    _, source = TokenSource.NONE, TokenSource.NONE
    msg = TokenSource.NONE.suggestion()
    assert "GITHUB_TOKEN" in msg
    assert "gh auth login" in msg


def test_token_source_suggestion_env():
    assert TokenSource.ENV.suggestion() == ""


def test_token_source_suggestion_gh_cli():
    assert TokenSource.GH_CLI.suggestion() == ""
