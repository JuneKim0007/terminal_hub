# /th:cmd-map

<!-- LOAD ANNOUNCEMENT: At the very start of this command, output exactly:
     🟢 Loaded: cmd-map — `extensions/gh_management/github_planner/commands/cmd-map.md`
     Do this before any tool calls. -->

Shows all command `.md` files, which skills each command loads, and which MCP tools it references.

## Flow

1. Call `build_docs_map()` — scans skills/ and commands/, writes docs_map.json
2. Call `get_docs_map(view="commands")` — returns formatted table
3. Print `_display` verbatim

## When to use

- "show me all commands"
- "what does command X depend on"
- "which commands use skill X"
- "command map"
- "cmd map"
