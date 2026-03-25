"""settings extension — conversational settings manager for terminal-hub.

No MCP tools — this plugin is command-only. The scanning and writing
of settings values is done by Claude using Read/Edit/Bash tools directly.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """No tools to register — command-only plugin."""
    pass
