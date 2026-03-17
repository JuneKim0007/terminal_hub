"""Shared pytest fixtures for the terminal-hub test suite."""
import pytest

from extensions.github_planner import (
    _ANALYSIS_CACHE,
    _FILE_TREE_CACHE,
    _PROJECT_DOCS_CACHE,
    _SESSION_HEADER_CACHE,
)
from extensions.github_planner.auth import invalidate_token_cache


@pytest.fixture(autouse=True)
def clear_all_caches():
    """Clear every module-level cache before and after each test."""
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    _FILE_TREE_CACHE.clear()
    _SESSION_HEADER_CACHE.clear()
    invalidate_token_cache()
    yield
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    _FILE_TREE_CACHE.clear()
    _SESSION_HEADER_CACHE.clear()
    invalidate_token_cache()
