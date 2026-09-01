"""Optional plugin hooks.

``register(mcp)`` lets a plugin add tools. These let the host ask plugins for
things it must not know how to compute itself:

  on_workspace_configured(root, github_repo)  -> str | None
      A workspace was just set up. Do any per-plugin work and optionally
      return a warning for the user.

  disk_state_items(root)                      -> list[dict]
      Rows describing on-disk artefacts this plugin owns, for /th:current-stat.

  cache_status()                              -> dict[str, str]
      In-memory cache names mapped to a short status string.

All three are optional: a plugin defines only what it needs. The host used to
import github_planner by name for exactly these three jobs, which defeated the
loader whose whole purpose is not knowing its plugins (R26).

A raising hook is contained and reported, never propagated — one plugin must
not be able to break setup_workspace or the state display.
"""
from __future__ import annotations

import importlib
from typing import Any

ON_WORKSPACE_CONFIGURED = "on_workspace_configured"
DISK_STATE_ITEMS = "disk_state_items"
CACHE_STATUS = "cache_status"


def _loaded_entry_modules() -> list[Any]:
    """Entry modules of the plugins loaded into this process.

    Reads terminal_hub.server.state rather than taking an argument so callers
    stay simple; the list is populated by create_server().
    """
    from terminal_hub.plugins.plugin_loader import discover_plugins
    from terminal_hub.config import EXTENSIONS_DIR
    import terminal_hub.server.state as state

    loaded = {e.get("name") for e in state._LOADED_EXTENSIONS}
    modules = []
    for manifest in discover_plugins(EXTENSIONS_DIR):
        if manifest.get("name") not in loaded:
            continue
        try:
            modules.append(importlib.import_module(manifest["entry"]))
        except Exception:  # noqa: BLE001 — a plugin that will not import is not our problem here
            continue
    return modules


def call_all(hook_name: str, *args, **kwargs) -> list[tuple[str, Any]]:
    """Call `hook_name` on every loaded plugin that defines it.

    Returns [(plugin_module_name, result)] for the ones that ran. A hook that
    raises is skipped rather than propagated: a misbehaving plugin must not
    take down the host operation that invoked it.
    """
    results: list[tuple[str, Any]] = []
    for module in _loaded_entry_modules():
        hook = getattr(module, hook_name, None)
        if not callable(hook):
            continue
        try:
            results.append((module.__name__, hook(*args, **kwargs)))
        except Exception:  # noqa: BLE001
            continue
    return results
