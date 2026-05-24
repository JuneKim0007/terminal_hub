"""Factory for the terminal-hub MCP server.

``create_server()`` returns a configured ``FastMCP`` instance:

  1. Discovers plugin manifests under ``extensions/``.
  2. Builds the instructions string Claude sees on connect.
  3. Registers the core ``terminal-hub://instructions`` resource and the
     four workspace-level tool groups (setup, announce, runtime state,
     plugin registry).
  4. Loads each discovered plugin (calls its ``register(mcp)`` entry).

The tool implementations live in ``server.tools.*`` — one module per
concern. Plugin-load warnings and per-extension tool inventories are
collected in ``server.state`` for later inspection.
"""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from terminal_hub.plugins.plugin_loader import (
    build_instructions,
    discover_plugins,
    load_plugin,
)
from terminal_hub.server import state as _state
from terminal_hub.server.builtins import _assert_builtins, _load_agent
from terminal_hub.server.tools import announce, plugin_registry, runtime_state, setup

# Fail fast at import time if a required builtin command file is missing.
_assert_builtins()

# extensions/ sits at the project root, three levels up from this file.
_EXTENSIONS_DIR = Path(__file__).resolve().parent.parent.parent / "extensions"


def create_server() -> FastMCP:
    """Create and return the configured FastMCP instance."""
    _state.reset()

    loaded_manifests = discover_plugins(_EXTENSIONS_DIR)
    instructions = build_instructions(loaded_manifests)
    mcp = FastMCP("terminal-hub", instructions=instructions)

    # ── Core resources ───────────────────────────────────────────────────────

    @mcp.resource("terminal-hub://instructions")
    def instructions_resource() -> str:
        """Full entry point instructions and tool reference."""
        return _load_agent("help.md")

    # ── Workspace-level tools ────────────────────────────────────────────────

    setup.register(mcp)
    announce.register(mcp)
    runtime_state.register(mcp)
    plugin_registry.register(mcp)

    # ── Dynamic plugin loading ───────────────────────────────────────────────

    tools_before: set[str] = set()
    if hasattr(mcp, "_tool_manager"):
        tools_before = {t.name for t in mcp._tool_manager.list_tools()}

    for manifest in loaded_manifests:
        err = load_plugin(manifest, mcp)
        if err:
            _state._PLUGIN_WARNINGS.append(err)
            continue
        tools_after: set[str] = set()
        if hasattr(mcp, "_tool_manager"):
            tools_after = {t.name for t in mcp._tool_manager.list_tools()}
        new_tools = sorted(tools_after - tools_before)
        _state._LOADED_EXTENSIONS.append({
            "name": manifest.get("name", "unknown"),
            "tools": new_tools,
            "manifest_path": str(manifest.get("_path", "")),
        })
        tools_before = tools_after

    return mcp
