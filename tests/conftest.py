"""Shared pytest fixtures for the terminal-hub test suite."""
import pytest

from extensions.gh_management.github_planner import (
    _ANALYSIS_CACHE,
    _FILE_TREE_CACHE,
    _LABEL_CACHE,
    _PROJECT_DOCS_CACHE,
    _REPO_CACHE,
    _SESSION_HEADER_CACHE,
    _invalidate_repo_cache,
)
from extensions.gh_management.github_planner.auth import invalidate_token_cache

import terminal_hub.workspace.locator as _locator


@pytest.fixture(autouse=True)
def clear_all_caches():
    """Clear every module-level cache and global before and after each test."""
    _locator._ACTIVE_PROJECT_ROOT = None
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    _FILE_TREE_CACHE.clear()
    _SESSION_HEADER_CACHE.clear()
    _LABEL_CACHE.clear()
    _invalidate_repo_cache()
    invalidate_token_cache()
    yield
    _locator._ACTIVE_PROJECT_ROOT = None
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    _FILE_TREE_CACHE.clear()
    _SESSION_HEADER_CACHE.clear()
    _LABEL_CACHE.clear()
    _invalidate_repo_cache()
    invalidate_token_cache()


# ── Network guard ─────────────────────────────────────────────────────────────
# The suite must not touch the network. test_setup_with_github_repo mocked the
# workspace but not the client, so setup_workspace ran gh.ensure_labels()
# against the real api.github.com — 5.6s of a 14s suite, and a failure whenever
# CI had no credentials or no route. This fixture makes that class of mistake
# fail loudly and immediately instead of passing slowly.
#
# A test that genuinely needs a socket must say so: @pytest.mark.network
@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    if request.node.get_closest_marker("network"):
        yield
        return

    import socket

    real_connect = socket.socket.connect

    def _blocked(self, address, *args, **kwargs):
        raise RuntimeError(
            f"Test opened a network connection to {address}. Mock the client "
            f"instead, or mark the test @pytest.mark.network if the call is "
            f"genuinely required."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    yield
    socket.socket.connect = real_connect
