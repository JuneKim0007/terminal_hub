"""``get_setup_status`` and ``setup_workspace`` MCP tools.

These cover the first contact between Claude and a project — checking
whether ``hub_agents/`` has been created and (if requested) wiring up a
GitHub repository.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from terminal_hub.config.env_store import _ensure_gitignored, read_env, write_env
from terminal_hub.config.settings import WorkspaceMode, load_config, save_config
from terminal_hub.workspace.locator import init_workspace, set_active_project_root


def register(mcp: FastMCP) -> None:
    """Attach setup-related tools to *mcp*."""
    # Late import — these names are patched at ``terminal_hub.server.*`` by
    # the test suite, so we go through the package every time.
    import terminal_hub.server as _srv

    @mcp.tool()
    def get_setup_status(project_root: str | None = None) -> dict:
        """Check if this project has been initialised. Always call this first.

        project_root: optional absolute path to the user's project directory.
        Pass Claude's actual working directory to ensure hub_agents/ is created
        in the correct location (not the MCP server's directory)."""
        if project_root is not None:
            set_active_project_root(project_root)
        root = _srv.get_workspace_root()
        hub_dir = root / "hub_agents"
        _G_INIT = "terminal-hub://workflow/init"
        if not hub_dir.exists():
            return {
                "initialised": False,
                "message": (
                    "hub_agents/ not found. "
                    "Ask the user if they want GitHub integration and call setup_workspace."
                ),
                "_guidance": _G_INIT,
            }
        cfg = load_config(root)
        env = read_env(root)
        result: dict = {
            "initialised": True,
            "mode": cfg["mode"] if cfg else "unknown",
            "github_repo": env.get("GITHUB_REPO"),
        }
        if _srv._PLUGIN_WARNINGS:
            result["plugin_warnings"] = list(_srv._PLUGIN_WARNINGS)
        return result

    @mcp.tool()
    def setup_workspace(github_repo: str | None = None, project_root: str | None = None) -> dict:
        """Initialise terminal-hub for this project.

        Creates hub_agents/, stores github_repo in hub_agents/.env if provided,
        and gitignores hub_agents/.

        github_repo: optional 'owner/repo' — omit for local-only mode.
        project_root: optional absolute path to the user's project directory."""
        from extensions.gh_management.github_planner.client import load_default_labels

        if project_root is not None:
            set_active_project_root(project_root)
        root = _srv.get_workspace_root()

        init_workspace(root)
        _ensure_gitignored(root)

        values: dict[str, str] = {}
        if github_repo:
            values["GITHUB_REPO"] = github_repo
        if values:
            write_env(root, values)

        mode = WorkspaceMode.GITHUB if github_repo else WorkspaceMode.LOCAL
        save_config(root, mode, github_repo)
        _srv._invalidate_repo_cache()  # new repo → flush cached detect_repo result

        label_warning: str | None = None
        if github_repo:
            gh, _ = _srv.get_github_client()
            if gh is not None:
                all_names = [d["name"] for d in load_default_labels()]
                with gh:
                    label_warning = gh.ensure_labels(all_names)

        repo = github_repo or "none"
        result: dict = {
            "success": True,
            "github_repo": github_repo,
            "hub_dir": str(root / "hub_agents"),
            "message": (
                f"Initialised hub_agents/ in {root}. "
                + (f"GitHub repo set to {github_repo}." if github_repo else "Running in local-only mode.")
            ),
            "_display": f"✓ Workspace initialised (mode: {mode.value}, repo: {repo})",
        }
        if label_warning:
            result["label_warning"] = label_warning
        return result
