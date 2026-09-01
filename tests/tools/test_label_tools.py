"""Tests for list_repo_labels and make_label."""
from unittest.mock import MagicMock, patch

import pytest

from extensions.gh_management.github_planner.labels import (
    _LABEL_ANALYSIS_CACHE,
    _LABEL_CACHE,
    _do_list_repo_labels,
    _do_make_label,
)

_RAW = [
    {"name": "bug", "color": "d73a4a", "description": "Something is broken"},
    {"name": "enhancement", "color": "a2eeef", "description": "New feature"},
]


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def gh_env(workspace):
    """Patch the workspace, env and a mock GitHub client into place."""
    def run(fn, gh=None, **kw):
        client = gh if gh is not None else MagicMock()
        client.__enter__ = lambda s: s
        client.__exit__ = MagicMock(return_value=False)
        with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}), \
             patch("extensions.gh_management.github_planner.get_github_client", return_value=(client, "")):
            return fn(client, **kw)
    return run


@pytest.fixture(autouse=True)
def _clear():
    _LABEL_CACHE.clear(); _LABEL_ANALYSIS_CACHE.clear()
    yield
    _LABEL_CACHE.clear(); _LABEL_ANALYSIS_CACHE.clear()


def test_list_labels_fetches_and_caches(gh_env):
    """The first call hits GitHub; the second is served from cache."""
    def go(client):
        client.list_labels.return_value = _RAW
        first = _do_list_repo_labels()
        second = _do_list_repo_labels()
        return first, second, client

    first, second, client = gh_env(go)

    assert first["names"] == ["bug", "enhancement"]
    assert first.get("cached") is not True
    assert second["cached"] is True
    assert client.list_labels.call_count == 1, "the cached call must not re-fetch"
    assert "bug — Something is broken" in second["_display"]


def test_list_labels_reports_a_github_failure(gh_env):
    def go(client):
        client.list_labels.side_effect = RuntimeError("boom")
        return _do_list_repo_labels()

    result = gh_env(go)
    assert result["error"] == "list_labels_failed"
    assert "boom" in result["message"]


def test_make_label_creates_and_drops_the_stale_cache(gh_env):
    """Creating a label must invalidate the cached label list."""
    _LABEL_CACHE["o/r"] = _RAW
    _LABEL_ANALYSIS_CACHE["o/r"] = {"active_labels": []}

    def go(client):
        client.create_label.return_value = {
            "name": "refactor", "color": "e4e669", "description": "Restructuring"
        }
        return _do_make_label("refactor", "e4e669", "Restructuring")

    result = gh_env(go)

    assert result["name"] == "refactor"
    assert "o/r" not in _LABEL_CACHE, "a new label invalidates the cached list"
    assert "o/r" not in _LABEL_ANALYSIS_CACHE


def test_make_label_requires_a_name(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        result = _do_make_label("", "d73a4a")
    assert result["error"] == "missing_field"


def test_make_label_reports_a_github_failure(gh_env):
    def go(client):
        client.create_label.side_effect = RuntimeError("rate limited")
        return _do_make_label("bug", "d73a4a")

    result = gh_env(go)
    assert result["error"] == "make_label_failed"
    assert "rate limited" in result["message"]
