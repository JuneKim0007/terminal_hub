# /th:skill-map

<!-- LOAD ANNOUNCEMENT: At the very start of this command, output exactly:
     🟢 Loaded: skill-map — `extensions/gh_management/github_planner/commands/skill-map.md`
     Do this before any tool calls. -->

Shows all skill `.md` files, which commands load them, whether they are always-loaded or on-demand, and their trigger phrases.

## Flow

1. Call `build_docs_map()` — scans skills/ and commands/, writes docs_map.json
2. Call `get_docs_map(view="skills")` — returns formatted table
3. Print `_display` verbatim

## When to use

- "show me all skills"
- "what skills exist"
- "which commands use skill X"
- "skill map"
