import pytest
import httpx
from unittest.mock import MagicMock, patch
from extensions.github_planner.client import GitHubClient, GitHubError, parse_error, load_default_labels


# ── parse_error ───────────────────────────────────────────────────────────────

def test_parse_error_401():
    err = parse_error(401, "Bad credentials")
    assert err["error"] == "auth_failed"
    assert "token" in err["message"].lower()


def test_parse_error_403():
    err = parse_error(403, "Resource not accessible")
    assert err["error"] == "permission_denied"
    assert "scope" in err["message"].lower()


def test_parse_error_404():
    err = parse_error(404, "Not Found")
    assert err["error"] == "repo_not_found"
    assert "GITHUB_REPO" in err["message"]


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


def test_create_issue_auth_failure_raises_with_message():
    client = make_client()
    resp = make_response(401, text="Bad credentials")
    with patch.object(client._client, "post", return_value=resp):
        with pytest.raises(GitHubError) as exc_info:
            client.create_issue(title="x", body="y", labels=[], assignees=[])
    assert exc_info.value.error_code == "auth_failed"
    assert "token" in str(exc_info.value).lower()


def test_create_issue_repo_not_found_raises_with_message():
    client = make_client()
    resp = make_response(404, text="Not Found")
    with patch.object(client._client, "post", return_value=resp):
        with pytest.raises(GitHubError) as exc_info:
            client.create_issue(title="x", body="y", labels=[], assignees=[])
    assert exc_info.value.error_code == "repo_not_found"
    assert "GITHUB_REPO" in str(exc_info.value)


def test_create_issue_network_error_raises_with_message():
    client = make_client()
    with patch.object(client._client, "post", side_effect=httpx.ConnectError("timeout")):
        with pytest.raises(GitHubError) as exc_info:
            client.create_issue(title="x", body="y", labels=[], assignees=[])
    assert exc_info.value.error_code == "network_error"
    assert "connect" in str(exc_info.value).lower() or "github" in str(exc_info.value).lower()


def test_client_sets_auth_header():
    client = GitHubClient(token="my-token", repo="o/r")
    assert client._client.headers["Authorization"] == "Bearer my-token"


def test_parse_error_429():
    err = parse_error(429, "rate limit exceeded")
    assert err["error"] == "rate_limited"
    assert "rate" in err["message"].lower() or "rate" in err["suggestion"].lower()


def test_create_issue_timeout_raises_with_message():
    import httpx
    client = make_client()
    with patch.object(client._client, "post", side_effect=httpx.TimeoutException("timed out")):
        with pytest.raises(GitHubError) as exc_info:
            client.create_issue(title="x", body="y", labels=[], assignees=[])
    assert exc_info.value.error_code == "timeout"
    assert "timed out" in str(exc_info.value).lower() or "timeout" in str(exc_info.value).lower()


def test_github_error_to_dict():
    err = GitHubError("something failed", error_code="auth_failed")
    d = err.to_dict()
    assert d["error"] == "auth_failed"
    assert d["message"] == "something failed"
    assert "_hook" not in d  # _hook is added by the call site in server.py, not by the exception


# ── _load_default_labels ──────────────────────────────────────────────────────

def test_load_default_labels_returns_list():
    labels = load_default_labels()
    assert isinstance(labels, list)
    assert len(labels) > 0


def test_load_default_labels_have_required_fields():
    for label in load_default_labels():
        assert "name" in label
        assert "color" in label


def test_load_default_labels_includes_bug_and_feature():
    names = {label["name"] for label in load_default_labels()}
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


# ── load_default_labels error paths ───────────────────────────────────────────

def test_load_default_labels_returns_empty_list_when_file_missing():
    """Lines 24-25: OSError path — file not found → returns []."""
    with patch("extensions.github_planner.client._LABELS_FILE") as mock_path:
        mock_path.read_text.side_effect = OSError("file not found")
        result = load_default_labels()
    assert result == []


def test_load_default_labels_returns_empty_list_when_corrupt():
    """Lines 24-25: JSONDecodeError path — bad JSON → returns []."""
    with patch("extensions.github_planner.client._LABELS_FILE") as mock_path:
        mock_path.read_text.return_value = "not valid json {"
        result = load_default_labels()
    assert result == []


# ── GitHubClient.close ────────────────────────────────────────────────────────

def test_close_closes_underlying_http_client():
    """Line 89: close() delegates to _client.close()."""
    client = make_client()
    with patch.object(client._client, "close") as mock_close:
        client.close()
    mock_close.assert_called_once()


# ── list_labels ────────────────────────────────────────────────────────────────

def test_list_labels_returns_empty_on_http_error():
    """Lines 122-130: HTTP error while listing labels → returns []."""
    client = make_client()
    resp = make_response(403)
    with patch.object(client._client, "get", return_value=resp):
        result = client.list_labels()
    assert result == []


def test_list_labels_returns_labels_on_success():
    """Lines 122-138: Happy path — single page of labels."""
    client = make_client()
    data = [{"name": "bug", "color": "d73a4a"}, {"name": "feature", "color": "a2eeef"}]
    resp = make_response(200, data)
    with patch.object(client._client, "get", return_value=resp):
        result = client.list_labels()
    assert len(result) == 2
    assert result[0]["name"] == "bug"


def test_list_labels_paginates_when_full_page():
    """Lines 134-138: len(data)==100 triggers next page fetch."""
    client = make_client()
    page1 = make_response(200, [{"name": f"label-{i}"} for i in range(100)])
    page2 = make_response(200, [{"name": "last-label"}])
    calls = iter([page1, page2])
    with patch.object(client._client, "get", side_effect=lambda *a, **kw: next(calls)):
        result = client.list_labels()
    assert len(result) == 101
    assert result[-1]["name"] == "last-label"


def test_list_labels_stops_on_empty_page():
    """Line 132-133: empty page breaks pagination loop."""
    client = make_client()
    resp = make_response(200, [])
    with patch.object(client._client, "get", return_value=resp):
        result = client.list_labels()
    assert result == []


# ── list_issues ────────────────────────────────────────────────────────────────

def test_list_issues_returns_issues():
    """Lines 142-145: Happy path — returns list of issue dicts."""
    client = make_client()
    data = [{"number": 1, "title": "Fix bug", "state": "open"}]
    resp = make_response(200, data)
    with patch.object(client._client, "get", return_value=resp):
        result = client.list_issues()
    assert len(result) == 1
    assert result[0]["number"] == 1


def test_list_issues_passes_state_and_per_page():
    """Lines 142-145: state and per_page params are forwarded."""
    client = make_client()
    resp = make_response(200, [])
    with patch.object(client._client, "get", return_value=resp) as mock_get:
        client.list_issues(state="closed", per_page=25)
    call_kwargs = mock_get.call_args[1]
    assert call_kwargs["params"]["state"] == "closed"
    assert call_kwargs["params"]["per_page"] == 25


# ── list_collaborators ────────────────────────────────────────────────────────

def test_list_collaborators_returns_empty_on_403():
    """Lines 151-152: 403 → return [] gracefully without raising."""
    client = make_client()
    resp = make_response(403)
    # 403 must NOT raise raise_for_status for this path — override it
    resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=resp):
        result = client.list_collaborators()
    assert result == []


def test_list_collaborators_returns_list_on_success():
    """Lines 149-154: Happy path — returns list of collaborators."""
    client = make_client()
    data = [{"login": "alice"}, {"login": "bob"}]
    resp = make_response(200, data)
    with patch.object(client._client, "get", return_value=resp):
        result = client.list_collaborators()
    assert len(result) == 2
    assert result[0]["login"] == "alice"


# ── _url ──────────────────────────────────────────────────────────────────────

def test_url_returns_method_and_full_url():
    """_url() builds method + BASE_URL + formatted path."""
    from extensions.github_planner.client import BASE_URL
    client = make_client()
    method, url = client._url("github", "list_labels")
    assert isinstance(method, str)
    assert url.startswith(BASE_URL)
    assert "owner/repo" in url


# ── get_labels: empty page break (line 169) ────────────────────────────────────

def test_get_labels_returns_empty_set_on_empty_page():
    """Line 169: when the first page is empty, get_labels breaks and returns empty set."""
    client = make_client()
    resp = make_response(200, [])
    with patch.object(client._client, "get", return_value=resp):
        result = client.get_labels()
    assert result == set()


# ── list_repo_tree ─────────────────────────────────────────────────────────────

def test_list_repo_tree_returns_blobs_only():
    client = make_client()
    tree_data = {
        "tree": [
            {"path": "src/auth.py", "type": "blob", "size": 200},
            {"path": "src/", "type": "tree", "size": 0},
            {"path": "README.md", "type": "blob", "size": 500},
        ]
    }
    resp = make_response(200, tree_data)
    with patch.object(client._client, "get", return_value=resp):
        result = client.list_repo_tree()

    assert len(result) == 2
    paths = {f["path"] for f in result}
    assert paths == {"src/auth.py", "README.md"}


def test_list_repo_tree_raises_on_auth_error():
    client = make_client()
    resp = make_response(401, {})
    with patch.object(client._client, "get", return_value=resp):
        with pytest.raises(GitHubError) as exc_info:
            client.list_repo_tree()
    assert exc_info.value.error_code == "auth_failed"


def test_list_repo_tree_raises_on_network_error():
    import httpx
    client = make_client()
    with patch.object(client._client, "get", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(GitHubError) as exc_info:
            client.list_repo_tree()
    assert exc_info.value.error_code == "network_error"


def test_list_repo_tree_empty_repo():
    client = make_client()
    resp = make_response(200, {"tree": []})
    with patch.object(client._client, "get", return_value=resp):
        result = client.list_repo_tree()
    assert result == []


# ── get_file_content ──────────────────────────────────────────────────────────

def _b64(text: str) -> str:
    import base64
    return base64.b64encode(text.encode()).decode()


def test_get_file_content_returns_decoded_text():
    client = make_client()
    resp = make_response(200, {"encoding": "base64", "content": _b64("hello world")})
    with patch.object(client._client, "get", return_value=resp):
        result = client.get_file_content("README.md")
    assert result == "hello world"


def test_get_file_content_raises_on_binary_encoding():
    client = make_client()
    resp = make_response(200, {"encoding": "none", "content": ""})
    with patch.object(client._client, "get", return_value=resp):
        with pytest.raises(GitHubError) as exc_info:
            client.get_file_content("image.png")
    assert exc_info.value.error_code == "binary_file"


def test_get_file_content_raises_on_too_large():
    import base64
    client = make_client()
    big = "x" * (101 * 1024)
    resp = make_response(200, {"encoding": "base64", "content": _b64(big)})
    with patch.object(client._client, "get", return_value=resp):
        with pytest.raises(GitHubError) as exc_info:
            client.get_file_content("big.py")
    assert exc_info.value.error_code == "file_too_large"


def test_get_file_content_raises_on_binary_bytes():
    import base64
    client = make_client()
    raw = bytes([0x80, 0x81, 0x82])
    content = base64.b64encode(raw).decode()
    resp = make_response(200, {"encoding": "base64", "content": content})
    with patch.object(client._client, "get", return_value=resp):
        with pytest.raises(GitHubError) as exc_info:
            client.get_file_content("binary.bin")
    assert exc_info.value.error_code == "binary_file"


def test_get_file_content_raises_on_404():
    client = make_client()
    resp = make_response(404, {})
    with patch.object(client._client, "get", return_value=resp):
        with pytest.raises(GitHubError) as exc_info:
            client.get_file_content("missing.py")
    assert exc_info.value.error_code == "repo_not_found"
