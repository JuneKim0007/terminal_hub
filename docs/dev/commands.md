# Slash Commands

How slash command `.md` files work and how to add new commands to a plugin.

---

## What a command file is

A command `.md` file is a Markdown prompt that gets loaded into Claude's context when a user invokes the corresponding slash command. It is not executed as code — it is read as instructions by Claude.

When a user types `/th:gh-plan`, Claude Code loads `~/.claude/commands/th/gh-plan.md` into context and Claude follows the instructions in that file.

---

## How commands get installed

`terminal-hub install` copies command files from the plugin directory to `~/.claude/commands/th/`:

```
extensions/plugin_creator/commands/create-plugin.md
    → ~/.claude/commands/th/create-plugin.md   → /th:create-plugin

extensions/gh_auxiliaries/commands/gh-auxiliaries.md
    → ~/.claude/commands/th/gh-auxiliaries.md   → /th:gh-auxiliaries

extensions/gh_auxiliaries/commands/gh-auxiliaries/code-of-conduct.md
    → ~/.claude/commands/th/gh-auxiliaries/code-of-conduct.md   → /th:gh-auxiliaries/code-of-conduct
```

Note: commands served by the MCP server (e.g. `/th:gh-plan`, `/th:gh-implementation`) are loaded via the `load_skill` MCP tool from the server's own file system — they are not copied from local `extensions/` during install.

**The `plugin.json` `commands` array is the authoritative install list.** Only files listed there are copied. If you create a new `.md` file but don't add it to `commands`, it will not be installed.

---

## plugin.json commands array

```json
{
  "commands": [
    "gh-plan.md",
    "gh-plan-create.md",
    "gh-docs.md"
  ]
}
```

After adding a new file to this array, re-run `terminal-hub install`.

---

## Command file conventions

### Load announcement

Every command should announce itself at the top before any tool calls:

```markdown
<!-- LOAD ANNOUNCEMENT: At the very start of this command, output exactly:
     🟢 Loaded: gh-auxiliaries — `extensions/gh_auxiliaries/commands/gh-auxiliaries.md`
     Do this before any tool calls. -->
```

This tells the user which command is active and where to find the file.

### Rule comments

Embed constraints as HTML comments — they are invisible in rendered markdown but Claude reads them:

```markdown
<!-- RULE: always call set_project_root(path=<cwd>) as the very first tool call -->
<!-- RULE: after any implementation action, do not narrate results verbosely -->
```

Rules are enforced by Claude following the instructions, not by Python.

### Step structure

Commands are structured as numbered steps. Each step is a heading:

```markdown
## Step 1 — Context switch (silent)

Call `set_project_root(path="<cwd>")`.
Call `apply_unload_policy(command="my-command")`.
Print `_display` verbatim.

## Step 2 — Load context

Call `load_project_docs(doc="summary")`.
```

### Skill loading

Commands load skills on demand:

```markdown
<!-- SKILL: load_skill("implementing") — contains workflow derivation rules -->
```

Or in the step body:

```markdown
Call `load_skill("design-principles")` and follow the doc update rules it returns.
```

---

## Sub-commands

Sub-commands are `.md` files in a subdirectory:

```
commands/
├── gh-implementation.md         → /th:gh-implementation
└── gh-implementation/
    └── implement.md             → /th:gh-implementation/implement
```

In `plugin.json`:

```json
{
  "commands": [
    "gh-implementation.md",
    "gh-implementation/implement.md"
  ]
}
```

---

## Namespace

All commands install under the `th` namespace, controlled by:

```python
# terminal_hub/namespace.py
COMMAND_NAMESPACE = "th"
```

The installed directory name determines the actual slash command prefix — changing `COMMAND_NAMESPACE` and re-running `terminal-hub install` renames all commands system-wide.

`description.json` command strings (e.g. `"/th:gh-plan"`) are informational labels only. They do not control the actual prefix — the directory name does. Update them for consistency when changing the namespace, but commands work regardless.
