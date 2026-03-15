import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from terminal_hub.auth import TokenSource, get_auth_options, resolve_token, verify_gh_cli_auth
from terminal_hub.github_client import GitHubClient
from terminal_hub.prompts import TERMINAL_HUB_INSTRUCTIONS
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

    return mcp
