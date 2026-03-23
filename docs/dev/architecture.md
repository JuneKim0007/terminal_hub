# Architecture

System design: how terminal-hub's MCP server, plugin loader, and FastMCP work together.

---

## Overview

terminal-hub is a Python MCP server that runs alongside Claude Code. Claude calls MCP tools; Python executes them and returns filtered results. Claude never reads raw config files — Python always processes data before returning it.

```
Claude Code
    │
    │  calls MCP tools
    ▼
terminal-hub (MCP server, stdio)
    │
    ├── plugin_loader.discover_plugins()
    │       reads extensions/*/plugin.json
    │       reads extensions/*/description.json
    │
    ├── github_planner plugin     register(mcp) → @mcp.tool() decorators
    ├── gh_implementation plugin  register(mcp) → @mcp.tool() decorators
    └── plugin_customization      register(mcp) → dispatch_task, model routing
```

---

## Startup sequence

```
terminal-hub (no subcommand)
    → __main__.py:main()
    → server.py:create_server()
        → FastMCP("terminal-hub")
        → discover_plugins(extensions/)
            for each extensions/*/plugin.json:
                validate_manifest()
                load description.json → manifest['_description']
        → load_plugin(manifest, mcp)
            importlib.import_module(manifest["entry"])
            module.register(mcp)   ← each plugin registers its tools here
        → server.run()  ← stdio MCP loop begins
```

---

## Plugin structure

Each plugin is a directory under `extensions/` with these files:

```
extensions/<plugin>/
├── plugin.json          # manifest: name, version, entry, commands_dir, commands[]
├── description.json     # user-facing: entry command, triggers, subcommands
├── __init__.py          # implements register(mcp) — all tools defined here
├── commands/            # slash command .md files
│   └── <name>.md
└── skills/              # reusable prompt fragments
    └── <name>.md
```

**plugin.json required fields:** `name`, `version`, `entry`, `commands_dir`, `commands`

The `commands` array is the authoritative list of files that `terminal-hub install` copies to `~/.claude/commands/th/`. A command not listed here will not be installed.

---

## Tool registration pattern

Every MCP tool follows this pattern:

```python
# extensions/my_plugin/__init__.py

def register(mcp) -> None:

    @mcp.tool()
    def my_tool(param: str) -> dict:
        """One-line description shown in Claude's tool list."""
        result = _do_my_tool(param)   # business logic in private function
        return {
            "data": result,
            "_display": f"✅ Done: {result}"   # shown to Claude as the readable result
        }

    def _do_my_tool(param: str) -> str:
        # actual work here — file I/O, JSON parsing, GitHub API calls
        ...
```

The `_do_*` / public split is intentional: it makes unit testing straightforward (test `_do_*` directly) and keeps the MCP registration layer thin.

The `_display` field is what Claude reads and narrates. The rest of the dict is structured data Claude can also use.

---

## Token efficiency layer

Python is the filter, not the pipe. Every tool processes data before returning:

- `apply_unload_policy("gh-implementation")` — reads `unload_policy.json`, clears caches in Python, returns one `_display` string. Claude never sees the policy JSON.
- `load_project_docs(doc="summary")` — returns only the summary doc content, not detail. Detail is fetched section-by-section via `lookup_feature_section`.
- `get_file_tree()` — cached with a 1-hour TTL; only rebuilds on explicit refresh or TTL expiry.

---

## hub_agents/ — per-project state

All state is written to `hub_agents/` in the user's project root (not the terminal-hub install directory). `set_project_root(path)` is called at the start of every command to ensure tools write to the right location.

`hub_agents/` is gitignored by default. Deleting it resets all state — terminal-hub rebuilds on next use.

---

## Plugin loader details

`plugin_loader.discover_plugins(plugins_dir)` scans two glob patterns:
- `extensions/*/plugin.json` — top-level plugins
- `extensions/*/*/plugin.json` — nested plugins (e.g. `extensions/gh_management/github_planner/`)

Required manifest fields are validated at load time. Invalid manifests are skipped with a stderr warning — the server still starts.

`description.json` is optional. If present, it populates the MCP server instructions string that tells Claude which commands exist and when to suggest them.
