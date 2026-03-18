import asyncio
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


# ── check_auth ────────────────────────────────────────────────────────────────

def test_check_auth_authenticated(workspace):
    from extensions.github_planner.auth import TokenSource
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=("mytoken", TokenSource.ENV)):
        server = create_server()
        result = call(server, "check_auth", {})
    assert result["authenticated"] is True
    assert result["source"] == "env"


def test_check_auth_not_authenticated(workspace):
    from extensions.github_planner.auth import TokenSource
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=(None, TokenSource.NONE)):
        server = create_server()
        result = call(server, "check_auth", {})
    assert result["authenticated"] is False
    assert "options" in result
    assert len(result["options"]) == 2


# ── verify_auth ───────────────────────────────────────────────────────────────

def test_verify_auth_success(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.verify_gh_cli_auth", return_value=(True, "Verified.")):
        server = create_server()
        result = call(server, "verify_auth", {})
    assert result["authenticated"] is True
    assert result["source"] == "gh_cli"


def test_verify_auth_failure(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.verify_gh_cli_auth", return_value=(False, "Run: gh auth login")):
        server = create_server()
        result = call(server, "verify_auth", {})
    assert result["authenticated"] is False
    assert "options" in result


# ── get_github_client ─────────────────────────────────────────────────────────

def test_submit_issue_no_repo_detected(workspace):
    """Cover get_github_client path where token exists but no repo is found."""
    import json
    from extensions.github_planner.auth import TokenSource
    from extensions.github_planner.storage import write_issue_file
    from datetime import date
    write_issue_file(root=workspace, slug="x", title="x", body="y",
                     assignees=[], labels=[], created_at=date.today())
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=("tok", TokenSource.ENV)), \
         patch("extensions.github_planner.detect_repo", return_value=None):
        server = create_server()
        result = call(server, "submit_issue", {"slug": "x"})
    assert result["error"] == "github_unavailable"


# ── write failure paths ───────────────────────────────────────────────────────

def test_update_project_description_write_failure(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.write_doc_file", side_effect=OSError("disk full")):
        server = create_server()
        result = call(server, "update_project_description", {"title": "X", "description": "desc"})
    assert result["error"] == "write_failed"
    assert "disk full" in result["message"]


def test_update_architecture_write_failure(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.write_doc_file", side_effect=OSError("disk full")):
        server = create_server()
        result = call(server, "update_architecture", {"overview": "layered arch"})
    assert result["error"] == "write_failed"
