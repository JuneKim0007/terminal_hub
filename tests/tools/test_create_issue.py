import asyncio
from datetime import date
from unittest.mock import MagicMock, patch
import pytest
from terminal_hub.server import create_server


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


def _mock_gh(number=1, url="https://github.com/o/r/issues/1"):
    mock = MagicMock()
    mock.create_issue.return_value = {"number": number, "html_url": url}
    return mock


def test_create_issue_writes_local_file(workspace):
    with patch("terminal_hub.server.get_github_client", return_value=(_mock_gh(), "")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "create_issue", {"title": "Fix auth bug", "body": "Fix it."})

    assert (workspace / "hub_agents" / "issues" / "fix-auth-bug.md").exists()
    assert result["issue_number"] == 1


def test_create_issue_returns_url(workspace):
    with patch("terminal_hub.server.get_github_client",
               return_value=(_mock_gh(42, "https://github.com/o/r/issues/42"), "")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "create_issue", {
            "title": "Add feature", "body": "body",
            "labels": ["enhancement"], "assignees": [],
        })
    assert result["issue_number"] == 42
    assert "issues/42" in result["url"]


def test_create_issue_returns_error_when_no_auth(workspace):
    with patch("terminal_hub.server.get_github_client", return_value=(None, "No auth found. Call check_auth.")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "create_issue", {"title": "Fix bug", "body": "body"})
    assert result["error"] == "github_unavailable"
    assert "check_auth" in result["suggestion"]


def test_create_issue_collision_resolved(workspace):
    # Pre-create the base slug file to force a -2 slug
    (workspace / "hub_agents" / "issues" / "fix-auth-bug.md").write_text("x")
    with patch("terminal_hub.server.get_github_client", return_value=(_mock_gh(), "")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "create_issue", {"title": "Fix auth bug", "body": "body"})
    assert (workspace / "hub_agents" / "issues" / "fix-auth-bug-2.md").exists()


def test_create_issue_github_error_returns_error(workspace):
    from terminal_hub.github_client import GitHubError
    mock_gh = MagicMock()
    mock_gh.create_issue.side_effect = GitHubError(
        "token rejected", error_code="auth_failed", suggestion="fix your token"
    )
    with patch("terminal_hub.server.get_github_client", return_value=(mock_gh, "")), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "create_issue", {"title": "x", "body": "y"})
    assert result["error"] == "auth_failed"
    assert "fix your token" in result["suggestion"]
