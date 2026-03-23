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
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_description", {
            "title": "My Project",
            "description": "A personal portfolio site.",
        })
    assert result["updated"] is True
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    text = (docs_dir / "project_summary.md").read_text()
    assert "My Project" in text
    assert "A personal portfolio site." in text
    assert "_display" in result
    assert "My Project" in result["_display"]


def test_update_project_description_returns_relative_path(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_description", {"title": "X", "description": "desc"})
    assert "hub_agents/extensions/gh_planner/project_summary.md" in result["file"]


def test_update_architecture_writes_file(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_architecture", {
            "overview": "Layered architecture with routes, services, and storage.",
            "components": ["Router", "Service layer", "Storage"],
        })
    assert result["updated"] is True
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    text = (docs_dir / "project_detail.md").read_text()
    assert "Layered architecture" in text
    assert "Router" in text
    assert "_display" in result
    assert result["_display"] == "✓ Architecture notes saved"


def test_update_docs_overwrite_preserves_latest(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "update_project_description", {"title": "V1", "description": "first"})
        call(server, "update_project_description", {"title": "V2", "description": "second"})
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    text = (docs_dir / "project_summary.md").read_text()
    assert "V2" in text
    assert "second" in text


# ── set_preference ────────────────────────────────────────────────────────────

def test_set_preference_confirm_arch_changes_true(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "set_preference", {"key": "confirm_arch_changes", "value": True})
    assert result["key"] == "confirm_arch_changes"
    assert result["value"] is True
    assert "on" in result["_display"]


def test_set_preference_confirm_arch_changes_false(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "set_preference", {"key": "confirm_arch_changes", "value": False})
    assert result["value"] is False
    assert "off" in result["_display"]


def test_set_preference_persisted_to_config(workspace):
    from terminal_hub.config import read_preference
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        call(server, "set_preference", {"key": "confirm_arch_changes", "value": True})
    assert read_preference(workspace, "confirm_arch_changes") is True


def test_set_preference_unknown_key_returns_error(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "set_preference", {"key": "nonexistent", "value": True})
    assert result["error"] == "unknown_preference"
    assert result["_hook"] is None


def test_set_preference_not_initialized_returns_needs_init(tmp_path):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "set_preference", {"key": "confirm_arch_changes", "value": True})
    assert result["status"] == "needs_init"


# ── create_github_repo ────────────────────────────────────────────────────────

def test_create_github_repo_success(workspace):
    from extensions.gh_management.github_planner.client import GitHubError
    fake_response = {"full_name": "alice/my-app", "html_url": "https://github.com/alice/my-app"}
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.resolve_token", return_value=("tok", object())), \
         patch("extensions.gh_management.github_planner.create_user_repo", return_value=fake_response):
        server = create_server()
        result = call(server, "create_github_repo", {"name": "my-app", "description": "A test app", "private": False})
    assert result["success"] is True
    assert result["github_repo"] == "alice/my-app"
    assert "alice/my-app" in result["_display"]


def test_create_github_repo_no_auth_returns_error(workspace):
    from unittest.mock import MagicMock
    no_token_source = MagicMock()
    no_token_source.suggestion.return_value = "No auth."
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.resolve_token", return_value=(None, no_token_source)):
        server = create_server()
        result = call(server, "create_github_repo", {"name": "x", "description": "y", "private": True})
    assert result["error"] == "github_unavailable"
    assert result["_hook"] is None


def test_create_github_repo_api_error_returns_error(workspace):
    from extensions.gh_management.github_planner.client import GitHubError
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.resolve_token", return_value=("tok", object())), \
         patch("extensions.gh_management.github_planner.create_user_repo", side_effect=GitHubError("name taken", error_code="validation_failed")):
        server = create_server()
        result = call(server, "create_github_repo", {"name": "taken", "description": "d", "private": True})
    assert result["error"] == "validation_failed"
    assert result["_hook"] is None


def test_create_github_repo_not_initialized_returns_needs_init(tmp_path):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=tmp_path):
        server = create_server()
        result = call(server, "create_github_repo", {"name": "x", "description": "y", "private": True})
    assert result["status"] == "needs_init"


# ── update_project_summary_section ────────────────────────────────────────────

def test_update_project_summary_section_creates_file(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_summary_section", {
            "section_name": "Milestones",
            "table_rows": [{"#": "M1", "Name": "Core Auth", "Delivers": "Users can sign up"}],
        })
    assert result["updated"] is True
    assert result["action"] == "created"
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    text = (docs_dir / "project_summary.md").read_text()
    assert "## Milestones" in text
    assert "Core Auth" in text


def test_update_project_summary_section_replaces_existing(workspace):
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text(
        "# Project\n\n## Milestones\n\nOld content\n\n## Design Principles\n\n- principle\n"
    )
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_summary_section", {
            "section_name": "Milestones",
            "items": ["M1 — Updated"],
        })
    assert result["action"] == "replaced"
    text = (docs_dir / "project_summary.md").read_text()
    assert "Updated" in text
    assert "Old content" not in text
    assert "Design Principles" in text  # other sections preserved


def test_update_project_summary_section_appends_new(workspace):
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# Project\n\n**Goal:** Build stuff\n")
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_summary_section", {
            "section_name": "Milestones",
            "items": ["M1 — Auth"],
        })
    assert result["action"] == "appended"
    text = (docs_dir / "project_summary.md").read_text()
    assert "Build stuff" in text  # original preserved
    assert "## Milestones" in text


def test_update_project_summary_section_empty_name_returns_error(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_summary_section", {
            "section_name": "",
            "items": ["some content"],
        })
    assert result["error"] == "invalid_input"


def test_update_project_summary_section_empty_content_returns_error(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "update_project_summary_section", {
            "section_name": "Milestones",
        })
    assert result["error"] == "invalid_input"


# ── apply_unload_policy enriched display (#138) ───────────────────────────────

def test_apply_unload_policy_display_has_emoji_lines(workspace):
    from extensions.gh_management.github_planner import _ANALYSIS_CACHE
    _ANALYSIS_CACHE["o/r"] = {"data": True}

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace):
        server = create_server()
        result = call(server, "apply_unload_policy", {"command": "gh-plan"})

    _ANALYSIS_CACHE.clear()
    assert result["success"] is True
    display = result["_display"]
    # Should contain emoji status indicators
    assert any(ch in display for ch in ["🗑️", "⚪", "🟢", "🔵"])
    assert "Unloaded:" in display
    assert "Kept:" in display


def test_read_doc_file_migrates_legacy_flat_path(workspace):
    """Legacy hub_agents/project_description.md is migrated to namespaced path on read."""
    from extensions.gh_management.github_planner.storage import read_doc_file, write_doc_file
    legacy = workspace / "hub_agents" / "project_description.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("old content")

    content = read_doc_file(workspace, "project_description")
    assert content == "old content"
    assert not legacy.exists()
    assert (workspace / "hub_agents" / "extensions" / "gh_planner" / "project_summary.md").exists()
