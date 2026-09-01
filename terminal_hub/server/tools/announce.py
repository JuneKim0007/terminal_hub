"""``announce_command_load`` — first call of every /th: command.

Surfaces which prompt file was loaded, how many MCP tools are registered,
and which extensions contributed them, so the user can see (and audit)
the entry-point handshake.
"""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from terminal_hub.plugins.plugin_loader import extension_summary


def register(mcp: FastMCP) -> None:
    """Attach announce_command_load to *mcp*."""
    import terminal_hub.server as _srv

    @mcp.tool()
    def announce_command_load(command: str) -> dict:
        """Announce that a /th: command prompt has been loaded.
        Call this as the very first step of every /th: command before any other tool.

        command: the command path relative to th/, e.g. 'github-planner' or
                 'github-planner/create-issue'."""
        commands_root = Path.home() / ".claude" / "commands" / "th"
        prompt_path = commands_root / (command + ".md")

        try:
            registered_tools = [t.name for t in mcp._tool_manager.list_tools()]
        except Exception:
            registered_tools = []

        ext_lines = []
        for ext in _srv._LOADED_EXTENSIONS:
            n = len(ext["tools"])
            desc = extension_summary(ext.get("manifest_path", ""))
            summary = f" — {desc}" if desc else ""
            ext_lines.append(f"  • {ext['name']}{summary} ({n} tool{'s' if n != 1 else ''})")

        exists = prompt_path.exists()
        path_str = str(prompt_path)

        display_lines = [
            f"🟢 /th:{command} — prompt loaded",
            f"   Prompt: {path_str}",
            f"   Tools:  {len(registered_tools)} registered",
        ]
        if ext_lines:
            display_lines.append("   Extensions:")
            display_lines.extend(ext_lines)
        if not exists:
            display_lines.append(f"   ⚠ prompt file not found at {path_str}")

        return {
            "command": command,
            "prompt_path": path_str,
            "prompt_exists": exists,
            "registered_tools": len(registered_tools),
            "loaded_extensions": list(_srv._LOADED_EXTENSIONS),
            "_display": "\n".join(display_lines),
        }
