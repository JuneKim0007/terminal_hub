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

Every name below is re-exported because something reads it *through this
module* — the ``tools.*`` handlers do ``import terminal_hub.server as _srv``
and go through the attribute so tests can patch it, and the suite patches
``terminal_hub.server.get_workspace_root`` directly. A name with no such
reader does not belong here; import it from the module that defines it.
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

# ── Workspace root — the canonical resolver lives in terminal_hub.workspace.
# github_planner.setup.get_workspace_root is a pure alias for it, so importing
# it from there would make the host depend on a plugin for its own policy.
from terminal_hub.workspace import ensure_initialized
from terminal_hub.workspace import resolve_workspace_root as get_workspace_root

# ── github_planner re-exports — read via ``_srv.<name>`` by tools.* ──────────
# Both are genuinely GitHub-specific. They remain here because setup_workspace
# configures a repo and warms its labels; moving that branch behind a plugin
# hook is the rest of R16.
from extensions.gh_management.github_planner import (
    _invalidate_repo_cache,
    get_github_client,
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
    # workspace
    "get_workspace_root",
    # github_planner re-exports
    "get_github_client",
    "ensure_initialized",
    "_invalidate_repo_cache",
]
