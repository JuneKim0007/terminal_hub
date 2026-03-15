import os
from datetime import date
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from terminal_hub.auth import TokenSource, get_auth_options, resolve_token, verify_gh_cli_auth
from terminal_hub.config import WorkspaceMode, load_config, save_config
from terminal_hub.github_client import GitHubClient, GitHubError
from terminal_hub.prompts import TERMINAL_HUB_INSTRUCTIONS
from terminal_hub.slugify import slugify
from terminal_hub.storage import (
    list_issue_files,
    read_doc_file,
    read_issue_file,
    resolve_slug,
    write_doc_file,
    write_issue_file,
)
from terminal_hub.workspace import detect_repo, init_workspace


def get_workspace_root() -> Path:
    return Path.cwd()


def get_github_client() -> tuple[GitHubClient | None, str]:
    """Return (client, error_message). Client is None if auth unavailable.

    error_message is Claude-readable with a suggestion if client is None.
    """
    token, source = resolve_token()
    if token is None:
        return None, source.suggestion()

    root = get_workspace_root()
    repo = os.environ.get("GITHUB_REPO") or detect_repo(root)
    if not repo:
        return None, (
            "No GitHub repo detected. Set GITHUB_REPO=owner/repo in your MCP config env, "
            "or run from a directory with a git remote set."
        )

    return GitHubClient(token=token, repo=repo), ""


def create_server() -> FastMCP:
    mcp = FastMCP("terminal-hub")

    # Auto-init workspace on startup
    init_workspace(get_workspace_root())

    @mcp.prompt()
    def terminal_hub_instructions() -> str:
        return TERMINAL_HUB_INSTRUCTIONS

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
        }

    # ── Issue tools ───────────────────────────────────────────────────────────

    @mcp.tool()
    def create_issue(
        title: str,
        body: str,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict:
        """Create a GitHub issue and save context locally.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        gh, error_msg = get_github_client()

        if gh is None:
            return {
                "error": "github_unavailable",
                "message": error_msg,
                "suggestion": "Call check_auth to present login options to the user.",
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
        """Return all tracked issues from local .terminal_hub/issues/ files.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        return {"issues": list_issue_files(root)}

    @mcp.tool()
    def get_issue_context(slug: str) -> dict:
        """Read a specific issue file by slug to reload context cheaply.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
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
        """Overwrite project_description.md. Call get_project_context first to preserve existing content.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        try:
            path = write_doc_file(root, "project_description", content)
            return {"updated": True, "file": str(path.relative_to(root))}
        except OSError as exc:
            return {"error": "write_failed", "message": str(exc)}

    @mcp.tool()
    def update_architecture(content: str) -> dict:
        """Overwrite architecture_design.md. Call get_project_context first to preserve existing content.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        try:
            path = write_doc_file(root, "architecture", content)
            return {"updated": True, "file": str(path.relative_to(root))}
        except OSError as exc:
            return {"error": "write_failed", "message": str(exc)}

    @mcp.tool()
    def get_project_context(file: str) -> dict:
        """Read project_description.md and/or architecture_design.md.
        file: 'project_description', 'architecture', or 'all'.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
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
        """Check if this project is configured. Call at session start.
        If configured=False, present the options to the user and call setup_workspace.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        cfg = load_config(root)
        if cfg is None:
            return {
                "configured": False,
                "options": [
                    {"value": "local", "label": "Local — track plans and issues on this machine only"},
                    {"value": "github", "label": "GitHub (new repo) — create a new GitHub repository"},
                    {"value": "connect", "label": "Connect — link to an existing GitHub repository"},
                ],
            }
        return {"configured": True, "mode": cfg["mode"], "repo": cfg.get("repo")}

    @mcp.tool()
    def setup_workspace(
        mode: str,
        repo: str | None = None,
    ) -> dict:
        """Configure the workspace for this project.
        mode: 'local', 'github' (new repo), or 'connect' (existing repo).
        repo: required for 'github' and 'connect' modes (format: owner/repo-name).
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        valid_modes = {"local", "github", "connect"}
        if mode not in valid_modes:
            return {
                "error": "invalid_mode",
                "message": f"mode must be one of: {', '.join(sorted(valid_modes))}",
            }
        if mode in ("github", "connect") and not repo:
            return {
                "error": "missing_repo",
                "message": f"repo (owner/repo-name) is required for mode '{mode}'",
            }
        workspace_mode = WorkspaceMode.LOCAL if mode == "local" else WorkspaceMode.GITHUB
        save_config(root, workspace_mode, repo)
        return {"success": True, "mode": mode, "repo": repo}

    return mcp
