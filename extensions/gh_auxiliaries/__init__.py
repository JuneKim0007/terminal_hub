"""gh_auxiliaries — community standards file generators for terminal-hub.

Registers MCP tools for generating GitHub community files (Code of Conduct,
Security Policy, PR/Issue templates, .gitignore) on explicit user request.
"""
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register gh_auxiliaries MCP tools.

    Currently a stub — tool implementations tracked in GitHub issues #201+.
    """
    # No tools registered yet; command routing is handled via .md slash commands.
    pass
