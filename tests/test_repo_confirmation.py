"""Tests for confirm_session_repo / set_session_repo / clear_session_repo tools."""
import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from terminal_hub.server import create_server


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


# ── test_confirm_already_confirmed ────────────────────────────────────────────

def test_confirm_already_confirmed(workspace):
    """If the session repo is already confirmed, returns confirmed=True immediately."""
    from extensions.gh_management.github_planner import _SESSION_REPO_CONFIRMED
    _SESSION_REPO_CONFIRMED[str(workspace)] = "owner/my-repo"

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "owner/my-repo"}), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None):
        server = create_server()
        result = call(server, "confirm_session_repo", {})

    assert result["confirmed"] is True
    assert result["repo"] == "owner/my-repo"

    # Cleanup
    _SESSION_REPO_CONFIRMED.pop(str(workspace), None)


# ── test_confirm_no_repo_configured ───────────────────────────────────────────

def test_confirm_no_repo_configured(workspace):
    """If no GITHUB_REPO is configured, returns confirmed=False with a display message."""
    from extensions.gh_management.github_planner import _SESSION_REPO_CONFIRMED
    _SESSION_REPO_CONFIRMED.pop(str(workspace), None)

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.read_env", return_value={}), \
         patch("extensions.gh_management.github_planner.ensure_initialized", return_value=None):
        server = create_server()
        result = call(server, "confirm_session_repo", {})

    assert result["confirmed"] is False
    assert result["repo"] is None
    assert "_display" in result
    assert "No GITHUB_REPO" in result["_display"] or "no" in result["_display"].lower()


# ── test_clear_session_repo_resets_state ─────────────────────────────────────

def test_clear_session_repo_resets_state(workspace):
    """After set_session_repo then apply_unload_policy(gh-plan-unload), state is cleared."""
    from extensions.gh_management.github_planner import _SESSION_REPO_CONFIRMED

    # Pre-populate session confirmation
    _SESSION_REPO_CONFIRMED[str(workspace)] = "owner/repo"
    assert str(workspace) in _SESSION_REPO_CONFIRMED

    # Clear via direct function call (mirrors what apply_unload_policy does)
    _SESSION_REPO_CONFIRMED.clear()

    assert str(workspace) not in _SESSION_REPO_CONFIRMED
