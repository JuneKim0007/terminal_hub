"""Plugin discovery, loading, and extension command runners.

`plugin_loader` reads `extensions/*/plugin.json` manifests and calls
`register(mcp)` on each entry module. `extension_loader` handles the
shell-command extension registry described in `command_config.json`.
"""
from terminal_hub.plugins.plugin_loader import (
    build_instructions,
    discover_plugins,
    load_plugin,
    validate_manifest,
)

__all__ = [
    "discover_plugins",
    "load_plugin",
    "build_instructions",
    "validate_manifest",
]
