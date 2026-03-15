import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from terminal_hub.auth import TokenSource, resolve_token
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

    return mcp
