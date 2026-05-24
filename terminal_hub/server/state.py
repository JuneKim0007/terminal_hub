"""Process-level mutable buffers shared across server tool modules.

Each ``create_server()`` call resets and repopulates these lists. They
are exposed at ``terminal_hub.server._PLUGIN_WARNINGS`` /
``_LOADED_EXTENSIONS`` for tests and introspection tooling
(``get_runtime_state``, ``announce_command_load``).
"""
from __future__ import annotations

_PLUGIN_WARNINGS: list[str] = []
# Each entry: {"name": str, "tools": list[str], "manifest_path": str}
_LOADED_EXTENSIONS: list[dict] = []


def reset() -> None:
    """Clear both buffers — called at the top of ``create_server()``."""
    _PLUGIN_WARNINGS.clear()
    _LOADED_EXTENSIONS.clear()
