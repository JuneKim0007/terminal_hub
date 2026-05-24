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
