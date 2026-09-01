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


# ── Shared server (R17) ───────────────────────────────────────────────────────
# create_server() was called 228 times per run at 29ms each — 7.2s of a 9.2s
# suite spent rebuilding an identical FastMCP instance. 99% of that cost is
# registering 66 tools; discovery and instruction-building are 0.3ms, so
# caching anything smaller than the whole instance buys nothing.
#
# Sharing one instance is safe because the tool bodies are closures that resolve
# get_workspace_root() at CALL time, so a test's patches still apply. What is
# NOT safe is _state: create_server() resets and repopulates _LOADED_EXTENSIONS
# and _PLUGIN_WARNINGS, and three test modules assert on them. So the template
# snapshots those buffers and every handout restores them, which keeps tests
# order-independent.
#
# A test that patches registration-time behaviour — discover_plugins, say —
# needs a genuinely fresh build and must say so with @pytest.mark.fresh_server.
#
# This wrapper is installed at conftest import time, before any test module
# runs `from terminal_hub.server import create_server`, because that binding
# happens at import and a fixture-scoped monkeypatch would come too late.
import terminal_hub.server as _srv_mod
import terminal_hub.server.app as _app_mod
import terminal_hub.server.state as _state_mod

_real_create_server = _app_mod.create_server
_server_template: dict = {}
_want_fresh = {"on": False}


def _shared_create_server():
    if _want_fresh["on"]:
        return _real_create_server()
    if "built" not in _server_template:
        server = _real_create_server()
        _server_template["built"] = (
            server,
            list(_state_mod._LOADED_EXTENSIONS),
            list(_state_mod._PLUGIN_WARNINGS),
        )
    server, extensions, warnings = _server_template["built"]
    _state_mod._LOADED_EXTENSIONS[:] = extensions
    _state_mod._PLUGIN_WARNINGS[:] = warnings
    return server


_app_mod.create_server = _shared_create_server
_srv_mod.create_server = _shared_create_server


@pytest.fixture(autouse=True)
def _server_freshness(request):
    """Honour @pytest.mark.fresh_server for tests that patch registration."""
    _want_fresh["on"] = request.node.get_closest_marker("fresh_server") is not None
    yield
    _want_fresh["on"] = False
