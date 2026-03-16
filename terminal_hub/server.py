import os
from datetime import date
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from terminal_hub.auth import TokenSource, get_auth_options, resolve_token, verify_gh_cli_auth
from terminal_hub.config import WorkspaceMode, load_config, save_config
from terminal_hub.env_store import read_env, write_env
from terminal_hub.github_client import GitHubClient, GitHubError
from terminal_hub.slugify import slugify
from terminal_hub.storage import (
    list_issue_files,
    read_doc_file,
    read_issue_file,
    resolve_slug,
    write_doc_file,
    write_issue_file,
)
from terminal_hub.workspace import detect_repo, init_workspace, resolve_workspace_root

_AGENTS_DIR = Path(__file__).parent.parent / "agents"

# ── Guidance URIs ─────────────────────────────────────────────────────────────
_G_INIT   = "terminal-hub://workflow/init"
_G_ISSUE  = "terminal-hub://workflow/issue"
_G_CONTEXT = "terminal-hub://workflow/context"
_G_AUTH   = "terminal-hub://workflow/auth"


def _load_agent(name: str) -> str:
    path = _AGENTS_DIR / name
    return path.read_text() if path.exists() else ""


def get_workspace_root() -> Path:
    return resolve_workspace_root()


def ensure_initialized(root: Path) -> dict | None:
    """Return a needs_init response if hub_agents/ is absent, else None."""
    if not (root / "hub_agents").exists():
        return {
            "status": "needs_init",
            "message": (
                "This project hasn't been set up with terminal-hub yet. "
                "Ask the user: would they like GitHub integration? If yes, what is their repo (owner/repo format)? "
                "Then call setup_workspace to initialise."
            ),
            "_guidance": _G_INIT,
        }
    return None


def get_github_client() -> tuple[GitHubClient | None, str]:
    """Return (client, error_message). Client is None if auth unavailable."""
    token, source = resolve_token()
    if token is None:
        return None, source.suggestion()

    root = get_workspace_root()
    repo = detect_repo(root)
    if not repo:
        return None, (
            "No GitHub repo configured for this project. "
            "Call setup_workspace with github_repo='owner/repo' to set one."
        )

    return GitHubClient(token=token, repo=repo), ""


def create_server() -> FastMCP:
    mcp = FastMCP("terminal-hub", instructions=_load_agent("entry_point.md"))

    # ── Resources (workflow guides) ───────────────────────────────────────────

    @mcp.resource("terminal-hub://instructions")
    def instructions_resource() -> str:
        """Full entry point instructions and tool reference."""
        return _load_agent("entry_point.md")

    @mcp.resource("terminal-hub://workflow/init")
    def workflow_init() -> str:
        """Step-by-step guide for initialising a new project workspace."""
        return _load_agent("workflow_init.md")

    @mcp.resource("terminal-hub://workflow/issue")
    def workflow_issue() -> str:
        """Guide for creating, listing, and reloading issue context."""
        return _load_agent("workflow_issue.md")

    @mcp.resource("terminal-hub://workflow/context")
    def workflow_context() -> str:
        """Guide for loading and saving project description and architecture."""
        return _load_agent("workflow_context.md")

    @mcp.resource("terminal-hub://workflow/auth")
    def workflow_auth() -> str:
        """Auth recovery guide — check_auth → gh auth login → verify_auth."""
        return _load_agent("workflow_auth.md")

    # ── Auth tools ────────────────────────────────────────────────────────────

    @mcp.tool()
    def check_auth() -> dict:
        """Check GitHub authentication status.
        If not authenticated, presents login options to show the user.
        Call this whenever a GitHub tool returns an auth error."""
        token, source = resolve_token()
        if token:
            return {
                "authenticated": True,
                "source": source.value,
                "message": f"Authenticated via {source.value.replace('_', ' ')}.",
            }
        return {
            "authenticated": False,
            "message": "No GitHub authentication found.",
            "options": get_auth_options(),
            "_guidance": _G_AUTH,
        }

    @mcp.tool()
    def verify_auth() -> dict:
        """Verify GitHub CLI authentication after the user runs gh auth login.
        Call this after the user reports they have completed gh auth login."""
        success, message = verify_gh_cli_auth()
        if success:
            return {
                "authenticated": True,
                "source": "gh_cli",
                "message": message,
            }
        return {
            "authenticated": False,
            "message": message,
            "options": get_auth_options(),
            "_guidance": _G_AUTH,
        }

    # ── Issue tools ───────────────────────────────────────────────────────────

    @mcp.tool()
    def create_issue(
        title: str,
        body: str,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict:
        """Create a GitHub issue and save context locally in hub_agents/issues/."""
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err

        gh, error_msg = get_github_client()
        if gh is None:
            return {
                "error": "github_unavailable",
                "message": error_msg,
                "suggestion": "Call check_auth to present login options to the user.",
                "_guidance": _G_AUTH,
            }

        try:
            data = gh.create_issue(
                title=title,
                body=body,
                labels=labels or [],
                assignees=assignees or [],
            )
        except GitHubError as exc:
            return exc.to_dict()

        base_slug = slugify(title)
        slug = resolve_slug(root, base_slug)

        try:
            path = write_issue_file(
                root=root,
                slug=slug,
                title=title,
                issue_number=data["number"],
                github_url=data["html_url"],
                body=body,
                assignees=assignees or [],
                labels=labels or [],
                created_at=date.today(),
            )
            local_file = str(path.relative_to(root))
        except OSError as exc:
            return {
                "issue_number": data["number"],
                "url": data["html_url"],
                "local_file": None,
                "warning": "local_write_failed",
                "warning_message": f"Issue created on GitHub but local file could not be written: {exc}",
            }

        return {
            "issue_number": data["number"],
            "url": data["html_url"],
            "local_file": local_file,
        }

    @mcp.tool()
    def list_issues() -> dict:
        """Return all tracked issues from local hub_agents/issues/ files."""
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err
        return {"issues": list_issue_files(root)}

    @mcp.tool()
    def get_issue_context(slug: str) -> dict:
        """Read a specific issue file by slug to reload context cheaply."""
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err
        content = read_issue_file(root, slug)
        if content is None:
            return {
                "error": "not_found",
                "message": f"No issue file found for slug '{slug}'. Use list_issues to see available slugs.",
            }
        return {"slug": slug, "content": content}

    # ── Project context tools ─────────────────────────────────────────────────

    @mcp.tool()
    def update_project_description(content: str) -> dict:
        """Overwrite hub_agents/project_description.md.
        Call get_project_context first to preserve existing content."""
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err
        try:
            path = write_doc_file(root, "project_description", content)
            return {"updated": True, "file": str(path.relative_to(root))}
        except OSError as exc:
            return {"error": "write_failed", "message": str(exc)}

    @mcp.tool()
    def update_architecture(content: str) -> dict:
        """Overwrite hub_agents/architecture_design.md.
        Call get_project_context first to preserve existing content."""
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err
        try:
            path = write_doc_file(root, "architecture", content)
            return {"updated": True, "file": str(path.relative_to(root))}
        except OSError as exc:
            return {"error": "write_failed", "message": str(exc)}

    @mcp.tool()
    def get_project_context(file: str) -> dict:
        """Read project_description.md and/or architecture_design.md from hub_agents/.
        file: 'project_description', 'architecture', or 'all'."""
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err
        if file == "all":
            return {
                "project_description": read_doc_file(root, "project_description"),
                "architecture": read_doc_file(root, "architecture"),
            }
        content = read_doc_file(root, file)
        return {"file": file, "content": content}

    # ── Workspace setup tools ─────────────────────────────────────────────────

    @mcp.tool()
    def get_setup_status() -> dict:
        """Check if this project has been initialised. Always call this first."""
        root = get_workspace_root()
        hub_dir = root / "hub_agents"
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
        return {
            "initialised": True,
            "mode": cfg["mode"] if cfg else "unknown",
            "github_repo": env.get("GITHUB_REPO"),
        }

    @mcp.tool()
    def setup_workspace(github_repo: str | None = None) -> dict:
        """Initialise terminal-hub for this project.

        Creates hub_agents/, stores github_repo in hub_agents/.env if provided,
        and gitignores hub_agents/.

        github_repo: optional 'owner/repo' — omit for local-only mode."""
        root = get_workspace_root()

        init_workspace(root)

        from terminal_hub.env_store import _ensure_gitignored
        _ensure_gitignored(root)

        values: dict[str, str] = {}
        if github_repo:
            values["GITHUB_REPO"] = github_repo

        if values:
            write_env(root, values)

        mode = WorkspaceMode.GITHUB if github_repo else WorkspaceMode.LOCAL
        save_config(root, mode, github_repo)

        return {
            "success": True,
            "github_repo": github_repo,
            "hub_dir": str(root / "hub_agents"),
            "message": (
                f"Initialised hub_agents/ in {root}. "
                + (f"GitHub repo set to {github_repo}." if github_repo else "Running in local-only mode.")
            ),
        }

    return mcp
