"""GitHub Planner plugin for terminal-hub.

Registers all GitHub-specific MCP tools and resources.
Call register(mcp) from create_server() to activate.
"""
# ── Re-exports for package-root importability ────────────────────────────────
from extensions.gh_management.github_planner.setup import (
    get_workspace_root,
    ensure_initialized,
    get_github_client,
    _G_AUTH,
    _load_agent,
    _invalidate_repo_cache,
    _REPO_CACHE,
)
# auth helpers re-exported at package root (server.py imports them here)
from extensions.gh_management.github_planner.auth import resolve_token, verify_gh_cli_auth

# Cache re-exports (used by tests/conftest.py and workspace_tools unload)
from extensions.gh_management.github_planner.analysis import (
    _ANALYSIS_CACHE,
    _FILE_TREE_CACHE,
    _DEFAULT_SCAN_PROFILE,
    _build_file_tree,
    _extract_file_index,
    _file_tree_cache_path,
    _is_markdown,
    _load_file_hashes,
    _load_scan_profile,
    _scan_profile_path,
    _should_ignore,
)
from extensions.gh_management.github_planner.project_docs import (
    _PROJECT_DOCS_CACHE,
    _SESSION_HEADER_CACHE,
    _docs_config_path,
    _gh_planner_docs_dir,
    _load_docs_config,
    _parse_h2_sections,
)
from extensions.gh_management.github_planner.labels import (
    _LABEL_CACHE,
    _LABEL_ANALYSIS_CACHE,
)
from extensions.gh_management.github_planner.milestones import (
    _MILESTONE_CACHE,
    _load_milestone_index,
    _milestone_knowledge_path,
    _milestones_dir,
)
from extensions.gh_management.github_planner.session import _SESSION_REPO_CONFIRMED
from extensions.gh_management.github_planner.skills import (
    _SKILL_REGISTRY,
    _load_skill_registry,
    _silent_skill_detection,
)
from extensions.gh_management.github_planner.issues import (
    _check_suggest_unload,
    _issues_cache_stale,
)
from extensions.gh_management.github_planner.workspace_tools import (
    _GH_PLANNER_VOLATILE_FILES,
    _load_unload_policy,
)
from extensions.gh_management.github_planner.project_docs import (
    _format_reuse_block,
    _preserve_reuse_block,
    _resolve_repo,
)
from extensions.gh_management.github_planner.milestones import (
    _ensure_milestone_label,
    _ensure_milestone_labels_for_all,
    _milestone_label_color,
    _MILESTONE_LABEL_PALETTE,
)
from extensions.gh_management.github_planner.skills import _parse_skills_dir
from extensions.gh_management.github_planner.storage import (
    write_doc_file,
    write_issue_file,
)
from extensions.gh_management.github_planner.client import create_user_repo
from terminal_hub.workspace import detect_repo
from terminal_hub.config.env_store import read_env
from pathlib import Path

# Plugin-level constants re-exported for patch compatibility in tests
from extensions.gh_management.github_planner.skills import (
    _PLUGIN_DIR,
    _COMMANDS_DIR,
)

# Alias for backward compat (_get_github_client was the old private name)
_get_github_client = get_github_client

# ── Domain module imports ─────────────────────────────────────────────────────
from extensions.gh_management.github_planner.session import (
    _do_check_auth,
    _do_verify_auth,
)
from extensions.gh_management.github_planner.labels import (
    _do_analyze_github_labels,
    _do_load_github_local_config,
    _do_load_github_global_config,
    _do_save_github_local_config,
    _do_get_github_config,
)
from extensions.gh_management.github_planner.milestones import (
    _do_generate_milestone_knowledge,
    _do_load_milestone_knowledge,
)
from extensions.gh_management.github_planner.issues import (
    _do_draft_issue,
    _do_submit_issue,
    _do_get_issue_context,
    _do_scan_issue_context,
    _do_generate_issue_workflows,
    _do_list_issues,
    _do_list_pending_drafts,
    _do_sync_github_issues,
)
from extensions.gh_management.github_planner.project_docs import (
    _do_update_project_detail_section,
    _do_save_project_docs,
    _do_load_project_docs,
    _do_docs_exist,
    _do_lookup_feature_section,
    _do_get_session_header,
)
from extensions.gh_management.github_planner.analysis import (
    _do_get_scan_profile_status,
    _do_create_scan_profile,
    _do_start_repo_analysis,
    _do_fetch_analysis_batch,
    _do_get_analysis_status,
    _do_get_file_tree,
    _do_analyze_repo_full,
)
from extensions.gh_management.github_planner.workspace_tools import (
    _do_save_docs_strategy,
    _do_load_docs_strategy,
    _do_search_project_docs,
    _do_connect_docs,
    _do_load_connected_docs,
    _do_list_plugin_state,
    _do_unload_plugin,
    _do_apply_unload_policy,
    detect_existing_docs,
)
from extensions.gh_management.github_planner.skills import (
    _do_load_skill,
    _do_update_skill_detection,
    _do_update_skill_create,
    _do_build_docs_map,
)

# Each domain module registers its own tools, so adding or changing one lands
# in a single file instead of two (R6).
from extensions.gh_management.github_planner.analysis import register_analysis_tools
from extensions.gh_management.github_planner.issues import register_issue_tools
from extensions.gh_management.github_planner.labels import register_label_tools
from extensions.gh_management.github_planner.milestones import register_milestone_tools
from extensions.gh_management.github_planner.project_docs import register_project_docs_tools
from extensions.gh_management.github_planner.session import register_session_tools
from extensions.gh_management.github_planner.setup import register_setup_tools
from extensions.gh_management.github_planner.skills import register_skill_tools
from extensions.gh_management.github_planner.workspace_tools import register_workspace_tools

__all__ = [
    # Everything above is re-exported on purpose: domain modules reach these
    # through _pkg(), and the suite patches many of them at
    # ``extensions.gh_management.github_planner.<name>``. Declaring them here
    # states that surface rather than leaving it to look like dead imports.
    "Path",
    "_ANALYSIS_CACHE",
    "_COMMANDS_DIR",
    "_DEFAULT_SCAN_PROFILE",
    "_FILE_TREE_CACHE",
    "_GH_PLANNER_VOLATILE_FILES",
    "_G_AUTH",
    "_LABEL_ANALYSIS_CACHE",
    "_LABEL_CACHE",
    "_MILESTONE_CACHE",
    "_MILESTONE_LABEL_PALETTE",
    "_PLUGIN_DIR",
    "_PROJECT_DOCS_CACHE",
    "_REPO_CACHE",
    "_SESSION_HEADER_CACHE",
    "_SESSION_REPO_CONFIRMED",
    "_SKILL_REGISTRY",
    "_build_file_tree",
    "_check_suggest_unload",
    "_do_analyze_github_labels",
    "_do_analyze_repo_full",
    "_do_apply_unload_policy",
    "_do_build_docs_map",
    "_do_check_auth",
    "_do_connect_docs",
    "_do_create_scan_profile",
    "_do_docs_exist",
    "_do_draft_issue",
    "_do_fetch_analysis_batch",
    "_do_generate_issue_workflows",
    "_do_generate_milestone_knowledge",
    "_do_get_analysis_status",
    "_do_get_file_tree",
    "_do_get_github_config",
    "_do_get_issue_context",
    "_do_get_scan_profile_status",
    "_do_get_session_header",
    "_do_list_issues",
    "_do_list_pending_drafts",
    "_do_list_plugin_state",
    "_do_load_connected_docs",
    "_do_load_docs_strategy",
    "_do_load_github_global_config",
    "_do_load_github_local_config",
    "_do_load_milestone_knowledge",
    "_do_load_project_docs",
    "_do_load_skill",
    "_do_lookup_feature_section",
    "_do_save_docs_strategy",
    "_do_save_github_local_config",
    "_do_save_project_docs",
    "_do_scan_issue_context",
    "_do_search_project_docs",
    "_do_start_repo_analysis",
    "_do_submit_issue",
    "_do_sync_github_issues",
    "_do_unload_plugin",
    "_do_update_project_detail_section",
    "_do_update_skill_create",
    "_do_update_skill_detection",
    "_do_verify_auth",
    "_docs_config_path",
    "_ensure_milestone_label",
    "_ensure_milestone_labels_for_all",
    "_extract_file_index",
    "_file_tree_cache_path",
    "_format_reuse_block",
    "_gh_planner_docs_dir",
    "_invalidate_repo_cache",
    "_is_markdown",
    "_issues_cache_stale",
    "_load_agent",
    "_load_docs_config",
    "_load_file_hashes",
    "_load_milestone_index",
    "_load_scan_profile",
    "_load_skill_registry",
    "_load_unload_policy",
    "_milestone_knowledge_path",
    "_milestone_label_color",
    "_milestones_dir",
    "_parse_h2_sections",
    "_parse_skills_dir",
    "_preserve_reuse_block",
    "_resolve_repo",
    "_scan_profile_path",
    "_should_ignore",
    "_silent_skill_detection",
    "create_user_repo",
    "detect_existing_docs",
    "detect_repo",
    "ensure_initialized",
    "get_github_client",
    "get_workspace_root",
    "read_env",
    "register_analysis_tools",
    "register_issue_tools",
    "register_label_tools",
    "register_milestone_tools",
    "register_project_docs_tools",
    "register_session_tools",
    "register_setup_tools",
    "register_skill_tools",
    "register_workspace_tools",
    "resolve_token",
    "verify_gh_cli_auth",
    "write_doc_file",
    "write_issue_file",
]

# ── Plugin registration ───────────────────────────────────────────────────────

def _register_resources(mcp) -> None:
    """Workflow guide resources."""

    @mcp.resource("terminal-hub://workflow/init")
    def workflow_init() -> str:
        """Step-by-step guide for initialising a new project workspace."""
        return _load_agent("gh-plan-setup.md")

    @mcp.resource("terminal-hub://workflow/issue")
    def workflow_issue() -> str:
        """Guide for creating, listing, and reloading issue context."""
        return _load_agent("gh-plan-create.md")

    @mcp.resource("terminal-hub://workflow/context")
    def workflow_context() -> str:
        """Guide for loading and saving project description and architecture."""
        return _load_agent("gh-plan.md")

    @mcp.resource("terminal-hub://workflow/auth")
    def workflow_auth() -> str:
        """Auth recovery guide — check_auth → gh auth login → verify_auth."""
        return _load_agent("gh-plan-auth.md")


def _register_workspace_root(mcp) -> None:
    """Active project-root override."""

    @mcp.tool()
    def set_project_root(path: str) -> dict:
        """Set the active project root so hub_agents/ is written to the user's project,
        not the MCP server's directory.

        MUST be the very first tool call in every /th: command.
        path: Claude's actual working directory (absolute path)."""
        from terminal_hub.workspace import set_active_project_root
        from terminal_hub.io.display import display as _text
        set_active_project_root(path)
        return {"root": str(path), "_display": _text("project_root.set", path=path)}

















































































def register(mcp) -> None:
    """Register all GitHub-specific MCP tools and resources on the given FastMCP instance."""
    _register_resources(mcp)
    _register_workspace_root(mcp)
    register_session_tools(mcp)
    register_issue_tools(mcp)
    register_project_docs_tools(mcp)
    register_analysis_tools(mcp)
    register_label_tools(mcp)
    register_milestone_tools(mcp)
    register_skill_tools(mcp)
    register_workspace_tools(mcp)
    register_setup_tools(mcp)
