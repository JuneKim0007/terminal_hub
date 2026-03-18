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


def test_update_project_description_writes_file(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_description", {"content": "# My Project\n"})
    assert result["updated"] is True
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    assert (docs_dir / "project_summary.md").read_text() == "# My Project\n"
    assert "_display" in result
    assert result["_display"] == "✓ Project description saved"


def test_update_project_description_returns_relative_path(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_description", {"content": "text"})
    assert "hub_agents/extensions/gh_planner/project_summary.md" in result["file"]


def test_update_architecture_writes_file(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_architecture", {"content": "# Architecture\n"})
    assert result["updated"] is True
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    assert (docs_dir / "project_detail.md").read_text() == "# Architecture\n"
    assert "_display" in result
    assert result["_display"] == "✓ Architecture notes saved"


def test_update_docs_overwrite_preserves_latest(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "update_project_description", {"content": "v1"})
        call(server, "update_project_description", {"content": "v2"})
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    assert (docs_dir / "project_summary.md").read_text() == "v2"


# ── set_preference ────────────────────────────────────────────────────────────

def test_set_preference_confirm_arch_changes_true(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "set_preference", {"key": "confirm_arch_changes", "value": True})
    assert result["key"] == "confirm_arch_changes"
    assert result["value"] is True
    assert "on" in result["_display"]


def test_set_preference_confirm_arch_changes_false(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "set_preference", {"key": "confirm_arch_changes", "value": False})
    assert result["value"] is False
    assert "off" in result["_display"]


def test_set_preference_persisted_to_config(workspace):
    from terminal_hub.config import read_preference
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "set_preference", {"key": "confirm_arch_changes", "value": True})
    assert read_preference(workspace, "confirm_arch_changes") is True


def test_set_preference_unknown_key_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "set_preference", {"key": "nonexistent", "value": True})
    assert result["error"] == "unknown_preference"
    assert result["_hook"] is None


def test_set_preference_not_initialized_returns_needs_init(tmp_path):
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "set_preference", {"key": "confirm_arch_changes", "value": True})
    assert result["status"] == "needs_init"


# ── create_github_repo ────────────────────────────────────────────────────────

def test_create_github_repo_success(workspace):
    from extensions.github_planner.client import GitHubError
    fake_response = {"full_name": "alice/my-app", "html_url": "https://github.com/alice/my-app"}
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=("tok", object())), \
         patch("extensions.github_planner.create_user_repo", return_value=fake_response):
        server = create_server()
        result = call(server, "create_github_repo", {"name": "my-app", "description": "A test app", "private": False})
    assert result["success"] is True
    assert result["github_repo"] == "alice/my-app"
    assert "alice/my-app" in result["_display"]


def test_create_github_repo_no_auth_returns_error(workspace):
    from unittest.mock import MagicMock
    no_token_source = MagicMock()
    no_token_source.suggestion.return_value = "No auth."
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=(None, no_token_source)):
        server = create_server()
        result = call(server, "create_github_repo", {"name": "x", "description": "y", "private": True})
    assert result["error"] == "github_unavailable"
    assert result["_hook"] is None


def test_create_github_repo_api_error_returns_error(workspace):
    from extensions.github_planner.client import GitHubError
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=("tok", object())), \
         patch("extensions.github_planner.create_user_repo", side_effect=GitHubError("name taken", error_code="validation_failed")):
        server = create_server()
        result = call(server, "create_github_repo", {"name": "taken", "description": "d", "private": True})
    assert result["error"] == "validation_failed"
    assert result["_hook"] is None


def test_create_github_repo_not_initialized_returns_needs_init(tmp_path):
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "create_github_repo", {"name": "x", "description": "y", "private": True})
    assert result["status"] == "needs_init"


def test_read_doc_file_migrates_legacy_flat_path(workspace):
    """Legacy hub_agents/project_description.md is migrated to namespaced path on read."""
    from extensions.github_planner.storage import read_doc_file, write_doc_file
    legacy = workspace / "hub_agents" / "project_description.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("old content")

    content = read_doc_file(workspace, "project_description")
    assert content == "old content"
    assert not legacy.exists()
    assert (workspace / "hub_agents" / "extensions" / "gh_planner" / "project_summary.md").exists()
