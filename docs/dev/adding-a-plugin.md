# Adding a Plugin

Step-by-step guide to creating a new terminal-hub plugin from scratch.

> **Shortcut:** run `/th:create-plugin` in Claude Code for guided conversational scaffolding that generates all these files for you.

---

## File structure

A plugin needs at minimum:

```
extensions/<your_plugin>/
├── plugin.json        # required — manifest
├── __init__.py        # required — register(mcp) + tool definitions
├── description.json   # recommended — slash command catalog
└── commands/
    └── start.md       # at least one command file
```

---

## Step 1 — Create the directory

```bash
mkdir -p extensions/my_plugin/commands
```

---

## Step 2 — Write plugin.json

```json
{
  "name": "my_plugin",
  "version": "0.1.0",
  "description": "What this plugin does in one sentence.",
  "entry": "extensions.my_plugin",
  "entry_command": "start.md",
  "commands_dir": "commands",
  "commands": ["start.md"]
}
```

**Key fields:**
- `entry` — Python module path used by `importlib.import_module()`
- `commands` — list of `.md` filenames to install. Only files listed here get copied to `~/.claude/commands/th/`.
- `entry_command` — the `.md` file that is the main entry point

---

## Step 3 — Implement register(mcp)

```python
# extensions/my_plugin/__init__.py

def register(mcp) -> None:

    @mcp.tool()
    def my_tool(input: str) -> dict:
        """Does something useful with input."""
        result = _do_my_tool(input)
        return {
            "result": result,
            "_display": f"✅ Done: {result}"
        }

    def _do_my_tool(input: str) -> str:
        return input.upper()
```

Rules:
- All tools must be defined inside `register(mcp)` — the function receives the FastMCP instance
- Use `@mcp.tool()` decorator; the docstring becomes the tool description in Claude's tool list
- Always return a dict with a `_display` field — this is what Claude reads and narrates
- Put business logic in `_do_*` private functions for testability

---

## Step 4 — Write description.json

```json
{
  "plugin": "my_plugin",
  "display_name": "My Plugin",
  "summary": "What this plugin does for the user.",
  "entry": {
    "command": "/th:my-plugin",
    "triggers": ["activate my plugin", "use my tool"],
    "use_when": "User wants to do the thing this plugin does"
  },
  "subcommands": []
}
```

This file is optional but recommended — it populates the MCP server instructions so Claude knows when to suggest your command.

---

## Step 5 — Write the command .md file

```markdown
# /th:my-plugin — My Plugin

<!-- LOAD ANNOUNCEMENT: At the very start, output exactly:
     🟢 Loaded: my-plugin — `extensions/my_plugin/commands/start.md`
     Do this before any tool calls. -->

You are in **my-plugin** mode.

## Step 1 — Do the thing

Call `my_tool(input="...")` and print `_display` verbatim.
```

See [commands.md](commands.md) for full command file conventions.

---

## Step 6 — Register and install

```bash
terminal-hub install
```

This copies `commands/start.md` to `~/.claude/commands/th/my-plugin.md`. Restart Claude Code — `/th:my-plugin` is now available.

---

## Step 7 — Add tests

```python
# tests/tools/test_my_plugin.py
import asyncio
from unittest.mock import patch
from terminal_hub.server import create_server

def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))

def test_my_tool_returns_display():
    server = create_server()
    result = call(server, "my_tool", {"input": "hello"})
    assert result["_display"] == "✅ Done: HELLO"
```

See [testing.md](testing.md) for patterns and coverage requirements.

---

## Adding skills to your plugin

Create `extensions/my_plugin/skills/<name>.md` with YAML frontmatter:

```markdown
---
name: my-skill
description: What this skill does — used to decide relevance.
alwaysApply: false
triggers:
  - phrase that triggers this skill
  - another trigger phrase
---

# my-skill

Skill content here — this is loaded into Claude's context when the skill is invoked.
```

Skills are loaded via `load_skill("my-skill")` from within a command file. See [skills-system.md](skills-system.md) for the full two-tier system.
