"""MCP server entrypoint and shared server-level symbols.

The server is split across small focused modules:

  - ``app``               — ``create_server()`` factory + plugin load loop
  - ``builtins``          — builtin command files (help.md, active.md, …)
  - ``state``             — process-level ``_PLUGIN_WARNINGS`` /
                            ``_LOADED_EXTENSIONS`` buffers
  - ``tools.setup``       — ``get_setup_status`` / ``setup_workspace``
  - ``tools.announce``    — ``announce_command_load``
  - ``tools.runtime_state`` — ``get_runtime_state``
  - ``tools.plugin_registry`` — ``scan_plugins`` / ``load_plugin_registry``

For backward compatibility (and because the test suite patches names like
``terminal_hub.server.get_workspace_root``), this ``__init__`` re-exports
the entire historical surface area of the old ``server.py`` module.
"""
# ── State buffers (populated as plugins load) ────────────────────────────────
from terminal_hub.server.state import _LOADED_EXTENSIONS, _PLUGIN_WARNINGS

# ── Builtins (path constants + helpers) ──────────────────────────────────────
from terminal_hub.server.builtins import (
    _BUILTIN_COMMANDS,
    _BUILTIN_DIR,
    _assert_builtins,
    _load_agent,
)

# ── Plugin discovery / loading (re-export for monkeypatching) ────────────────
from terminal_hub.plugins.plugin_loader import (
    build_instructions,
    discover_plugins,
    load_plugin,
)

# ── github_planner re-exports — tests patch at ``terminal_hub.server.*`` ─────
from extensions.gh_management.github_planner import (
    _invalidate_repo_cache,
    ensure_initialized,
    get_github_client,
    get_workspace_root,
    resolve_token,
    verify_gh_cli_auth,
)
from extensions.gh_management.github_planner.storage import (
    write_doc_file,
    write_issue_file,
)

# ── Public factory ───────────────────────────────────────────────────────────
from terminal_hub.server.app import create_server

__all__ = [
    "create_server",
    # builtins
    "_BUILTIN_DIR",
    "_BUILTIN_COMMANDS",
    "_load_agent",
    "_assert_builtins",
    # state
    "_PLUGIN_WARNINGS",
    "_LOADED_EXTENSIONS",
    # plugin loader re-exports
    "discover_plugins",
    "load_plugin",
    "build_instructions",
    # github_planner re-exports
    "get_workspace_root",
    "get_github_client",
    "ensure_initialized",
    "resolve_token",
    "verify_gh_cli_auth",
    "_invalidate_repo_cache",
    "write_issue_file",
    "write_doc_file",
]
