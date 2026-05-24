"""Per-tool MCP handler modules.

Each submodule exposes ``register(mcp)`` which attaches one or more
``@mcp.tool()`` handlers. ``server.app.create_server`` calls each
``register`` in turn.
"""
from terminal_hub.server.tools import (
    announce,
    plugin_registry,
    runtime_state,
    setup,
)

__all__ = ["setup", "announce", "runtime_state", "plugin_registry"]
