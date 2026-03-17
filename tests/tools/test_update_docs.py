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
