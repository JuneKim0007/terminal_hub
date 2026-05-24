"""``scan_plugins`` and ``load_plugin_registry`` MCP tools.

Together they keep ``hub_agents/plugin.config.json`` in sync with the
``description.json`` files under each ``extensions/*/`` directory.
``/th:converse`` and similar matchers read the registry to find which
plugin to suggest based on conversation triggers.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Attach scan_plugins and load_plugin_registry to *mcp*."""
    import terminal_hub.server as _srv

    @mcp.tool()
    def scan_plugins() -> dict:
        """Scan extensions/ for description.json files and build hub_agents/plugin.config.json (#44).

        Reads each extension's description.json (name, display_name, usage, commands, triggers).
        Writes a compact registry to hub_agents/plugin.config.json.
        Returns {plugins: [...], unidentified: N, total: N, _display: ...}.
        Use load_plugin_registry() to read the result without re-scanning.
        """
        root = _srv.get_workspace_root()
        if err := _srv.ensure_initialized(root):
            return err

        # extensions/ lives next to the terminal_hub package
        extensions_dir = Path(__file__).resolve().parent.parent.parent.parent / "extensions"
        plugins: list[dict] = []
        unidentified: list[str] = []

        for desc_path in sorted(extensions_dir.rglob("description.json")):
            try:
                raw = json.loads(desc_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            # Normalize to registry format — tolerate both old and new schema
            name = raw.get("plugin") or raw.get("name") or desc_path.parent.name
            display_name = raw.get("display_name") or name.replace("_", " ").title()
            usage = (
                raw.get("usage")
                or raw.get("summary")
                or (raw.get("entry") or {}).get("use_when")
                or ""
            )
            path = str(desc_path.parent.relative_to(extensions_dir.parent))

            # Commands: new-schema list or old-schema entry + subcommands
            commands: list[str] = raw.get("commands", [])
            if not commands:
                if entry := raw.get("entry"):
                    if cmd := entry.get("command"):
                        commands = [cmd]
                    for sub in raw.get("subcommands", []):
                        if cmd := sub.get("command"):
                            commands.append(cmd)

            # Triggers: new-schema list or old-schema entry.triggers
            triggers: list[str] = raw.get("triggers", [])
            if not triggers:
                if entry := raw.get("entry"):
                    triggers = entry.get("triggers", [])

            if not usage:
                unidentified.append(name)

            plugins.append({
                "name": name,
                "display_name": display_name,
                "path": path,
                "usage": usage,
                "commands": commands,
                "triggers": triggers,
                "has_description": bool(usage),
            })

        registry = {
            "last_scanned": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "plugins": plugins,
            "unidentified": unidentified,
        }

        config_path = root / "hub_agents" / "plugin.config.json"
        tmp = config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        os.replace(tmp, config_path)

        n = len(plugins)
        n_unid = len(unidentified)
        return {
            "plugins": plugins,
            "total": n,
            "unidentified": n_unid,
            "_display": (
                f"✓ Scanned {n} plugin(s), {n_unid} missing usage description\n"
                f"  Saved to hub_agents/plugin.config.json"
            ),
        }

    @mcp.tool()
    def load_plugin_registry(plugin: str | None = None) -> dict:
        """Load hub_agents/plugin.config.json for plugin matching (#44 / #45).

        Returns {plugins, unidentified, last_scanned} or suggests calling scan_plugins first.
        Each plugin entry: {name, display_name, usage, commands, triggers}.

        plugin: optional plugin name to filter by. When provided, returns only the
                matching entry (avoids loading the full registry into Claude's context).
                When omitted, returns all plugins (backward compatible).
        """
        root = _srv.get_workspace_root()
        if err := _srv.ensure_initialized(root):
            return err

        config_path = root / "hub_agents" / "plugin.config.json"
        if not config_path.exists():
            return {
                "plugins": [],
                "last_scanned": None,
                "_suggest_scan": (
                    "No plugin registry found. Call scan_plugins() to build it — "
                    "enables smart plugin suggestions via /th:converse."
                ),
            }

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"plugins": [], "last_scanned": None, "error": "registry_corrupt"}

        all_plugins = data.get("plugins", [])
        if plugin:
            filtered = [p for p in all_plugins if p.get("name") == plugin]
            return {
                "plugins": filtered,
                "unidentified": 0,
                "last_scanned": data.get("last_scanned"),
            }

        return {
            "plugins": all_plugins,
            "unidentified": len(data.get("unidentified", [])),
            "last_scanned": data.get("last_scanned"),
        }
