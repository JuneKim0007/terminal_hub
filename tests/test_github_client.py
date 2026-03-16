import pytest
import httpx
from unittest.mock import MagicMock, patch
from terminal_hub.github_client import GitHubClient, GitHubError, parse_error, _load_default_labels


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


def test_parse_error_429():
    err = parse_error(429, "rate limit exceeded")
    assert err["error"] == "rate_limited"
    assert "rate" in err["message"].lower() or "rate" in err["suggestion"].lower()


def test_create_issue_timeout_raises_with_suggestion():
    import httpx
    client = make_client()
    with patch.object(client._client, "post", side_effect=httpx.TimeoutException("timed out")):
        with pytest.raises(GitHubError) as exc_info:
            client.create_issue(title="x", body="y", labels=[], assignees=[])
    assert exc_info.value.error_code == "timeout"
    assert exc_info.value.suggestion is not None


def test_github_error_to_dict():
    err = GitHubError("something failed", error_code="auth_failed", suggestion="fix your token")
    d = err.to_dict()
    assert d["error"] == "auth_failed"
    assert d["suggestion"] == "fix your token"
    assert d["message"] == "something failed"


# ── _load_default_labels ──────────────────────────────────────────────────────

def test_load_default_labels_returns_list():
    labels = _load_default_labels()
    assert isinstance(labels, list)
    assert len(labels) > 0


def test_load_default_labels_have_required_fields():
    for label in _load_default_labels():
        assert "name" in label
        assert "color" in label


def test_load_default_labels_includes_bug_and_feature():
    names = {l["name"] for l in _load_default_labels()}
    assert "bug" in names
    assert "feature" in names


# ── get_labels ────────────────────────────────────────────────────────────────

def test_get_labels_returns_names():
    client = make_client()
    resp = make_response(200, [{"name": "bug"}, {"name": "feature"}])
    with patch.object(client._client, "get", return_value=resp):
        names = client.get_labels()
    assert names == {"bug", "feature"}


def test_get_labels_returns_empty_on_error():
    client = make_client()
    resp = make_response(403)
    with patch.object(client._client, "get", return_value=resp):
        names = client.get_labels()
    assert names == set()


def test_get_labels_paginates():
    client = make_client()
    # First page: 100 items; second page: 1 item
    page1 = make_response(200, [{"name": f"label-{i}"} for i in range(100)])
    page2 = make_response(200, [{"name": "extra"}])
    calls = iter([page1, page2])
    with patch.object(client._client, "get", side_effect=lambda *a, **kw: next(calls)):
        names = client.get_labels()
    assert "label-0" in names
    assert "extra" in names


# ── create_label ──────────────────────────────────────────────────────────────

def test_create_label_success():
    client = make_client()
    resp = make_response(201, {"name": "new-label"})
    with patch.object(client._client, "post", return_value=resp):
        ok = client.create_label("new-label", "ff0000", "A label")
    assert ok is True


def test_create_label_already_exists():
    client = make_client()
    # 422 means already exists — still considered success
    resp = make_response(422, text="already exists")
    with patch.object(client._client, "post", return_value=resp):
        ok = client.create_label("bug", "d73a4a", "Something isn't working")
    assert ok is True


def test_create_label_returns_false_on_http_error():
    client = make_client()
    with patch.object(client._client, "post", side_effect=httpx.ConnectError("fail")):
        ok = client.create_label("bad", "000000", "")
    assert ok is False


# ── ensure_labels ─────────────────────────────────────────────────────────────

def test_ensure_labels_empty_list_returns_none():
    client = make_client()
    result = client.ensure_labels([])
    assert result is None


def test_ensure_labels_all_exist_returns_none():
    client = make_client()
    with patch.object(client, "get_labels", return_value={"bug", "feature"}):
        result = client.ensure_labels(["bug", "feature"])
    assert result is None


def test_ensure_labels_creates_missing_known_label():
    client = make_client()
    with patch.object(client, "get_labels", return_value=set()):
        with patch.object(client, "create_label", return_value=True):
            result = client.ensure_labels(["bug"])
    assert result is None


def test_ensure_labels_returns_error_for_unknown_label():
    client = make_client()
    with patch.object(client, "get_labels", return_value=set()):
        result = client.ensure_labels(["totally-unknown-label-xyz"])
    assert result is not None
    assert "totally-unknown-label-xyz" in result


def test_ensure_labels_returns_error_when_create_fails():
    client = make_client()
    with patch.object(client, "get_labels", return_value=set()):
        with patch.object(client, "create_label", return_value=False):
            result = client.ensure_labels(["bug"])
    assert result is not None
    assert "bug" in result
