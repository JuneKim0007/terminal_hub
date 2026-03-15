import pytest
import httpx
from unittest.mock import MagicMock, patch
from terminal_hub.github_client import GitHubClient, GitHubError, parse_error


# ── parse_error ───────────────────────────────────────────────────────────────

def test_parse_error_401():
    err = parse_error(401, "Bad credentials")
    assert err["error"] == "auth_failed"
    assert "token" in err["suggestion"].lower()


def test_parse_error_403():
    err = parse_error(403, "Resource not accessible")
    assert err["error"] == "permission_denied"
    assert "scope" in err["suggestion"].lower()


def test_parse_error_404():
    err = parse_error(404, "Not Found")
    assert err["error"] == "repo_not_found"
    assert "GITHUB_REPO" in err["suggestion"]


def test_parse_error_422():
    err = parse_error(422, "Validation Failed")
    assert err["error"] == "validation_failed"


def test_parse_error_unknown():
    err = parse_error(500, "Internal Server Error")
    assert err["error"] == "github_error"
    assert "500" in err["message"]


# ── GitHubClient ──────────────────────────────────────────────────────────────

def make_client():
    return GitHubClient(token="test-token", repo="owner/repo")


def make_response(status_code, json_data=None, text=""):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    mock.text = text
    if status_code >= 400:
        mock.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=mock
        )
    else:
        mock.raise_for_status = MagicMock()
    return mock


def test_create_issue_success():
    client = make_client()
    resp = make_response(201, {"number": 42, "html_url": "https://github.com/owner/repo/issues/42"})
    with patch.object(client._client, "post", return_value=resp):
        result = client.create_issue(title="Fix bug", body="body", labels=[], assignees=[])
    assert result["number"] == 42
    assert result["html_url"] == "https://github.com/owner/repo/issues/42"


def test_create_issue_auth_failure_raises_with_suggestion():
    client = make_client()
    resp = make_response(401, text="Bad credentials")
    with patch.object(client._client, "post", return_value=resp):
        with pytest.raises(GitHubError) as exc_info:
            client.create_issue(title="x", body="y", labels=[], assignees=[])
    assert exc_info.value.suggestion is not None
    assert "token" in exc_info.value.suggestion.lower()


def test_create_issue_repo_not_found_raises_with_suggestion():
    client = make_client()
    resp = make_response(404, text="Not Found")
    with patch.object(client._client, "post", return_value=resp):
        with pytest.raises(GitHubError) as exc_info:
            client.create_issue(title="x", body="y", labels=[], assignees=[])
    assert exc_info.value.suggestion is not None
    assert "GITHUB_REPO" in exc_info.value.suggestion


def test_create_issue_network_error_raises_with_suggestion():
    client = make_client()
    with patch.object(client._client, "post", side_effect=httpx.ConnectError("timeout")):
        with pytest.raises(GitHubError) as exc_info:
            client.create_issue(title="x", body="y", labels=[], assignees=[])
    assert exc_info.value.suggestion is not None
    assert "network" in exc_info.value.suggestion.lower() or "connect" in exc_info.value.suggestion.lower()


def test_client_sets_auth_header():
    client = GitHubClient(token="my-token", repo="o/r")
    assert client._client.headers["Authorization"] == "Bearer my-token"


def test_github_error_to_dict():
    err = GitHubError("something failed", error_code="auth_failed", suggestion="fix your token")
    d = err.to_dict()
    assert d["error"] == "auth_failed"
    assert d["suggestion"] == "fix your token"
    assert d["message"] == "something failed"
