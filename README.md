# terminal-hub

An extensible plugin framework for Claude Code — pair MCP tools with Claude slash commands to build and share workflow plugins.

Ships with **github_planner**, a full GitHub issue management plugin, as the reference implementation.

---

## How it works

terminal-hub runs as an MCP server connected to Claude Code. Plugins register two things:

- **MCP tools** — Python functions Claude can call (fetch data, write files, call APIs)
- **Slash commands** — `.md` prompt files that load the conversational workflow

Both halves are required. The MCP server handles data; the slash commands handle conversation. Together they form a complete, self-contained workflow.

---

## Quick start

```bash
pip install terminal-hub
terminal-hub install    # registers MCP server + copies slash commands
# restart Claude Code
```

Then in Claude Code:

```
/github_planner:start
```

Claude runs the full GitHub planner — workspace setup, auth check, issue drafting, and repo analysis — all in one conversation.

---

## Bundled plugin: github_planner

The default plugin covers the full GitHub issue lifecycle:

| Command | What it does |
|---------|-------------|
| `/github_planner:start` | Guided session — setup → auth → menu loop |
| `/github_planner:create` | Draft and push a single GitHub issue |
| `/github_planner:analyze` | Snapshot label, assignee, and structure patterns |
| `/github_planner:inspect` | Show what terminal-hub context Claude is holding |
| `/github_planner:setup` | Configure workspace and GitHub repo |

---

## Conversation mode

You don't have to type a slash command. The MCP server is always running. When Claude detects GitHub planning intent in conversation, it offers to enable the plugin:

```
User: I want to track this bug as a GitHub issue.

Claude: It looks like you want to use GitHub issue planning.
        Would you like to enable github_planner? (yes / no)
```

---

## Writing a plugin

1. Create `plugins/<name>/` with `plugin.json` and `__init__.py`
2. In `__init__.py`, define `register(mcp)` and decorate tools with `@mcp.tool()`
3. Add slash command `.md` files to `plugins/<name>/commands/`
4. Run `terminal-hub install` to copy commands to Claude Code

```python
# plugins/my_plugin/__init__.py
def register(mcp) -> None:
    @mcp.tool()
    def my_tool(input: str) -> dict:
        """Does something useful."""
        return {"result": input.upper(), "_display": f"Done: {input.upper()}"}
```

```json
// plugins/my_plugin/plugin.json
{
  "name": "my_plugin",
  "version": "0.1.0",
  "description": "My custom workflow plugin",
  "entry": "plugins.my_plugin",
  "commands_dir": "commands",
  "commands": ["start.md"]
}
```

See `plugins/github_planner/` for a complete example.

---

## Plugin management commands

| Command | What it does |
|---------|-------------|
| `/tmh:create_plugin` | Conversational plugin builder — generates code + docs |
| `/tmh:read_<name>` | Analyze a plugin and generate `for_claude.md` docs |
| `/tmh:modify_<name>` | Conversational plugin modifier with context loading |

---

## Local state

All terminal-hub state lives in `hub_agents/` inside your project (gitignored):

```
hub_agents/
├── .env                      # GITHUB_REPO, optional GITHUB_TOKEN
├── config.yaml               # mode: local|github
├── issues/
│   └── <slug>.md             # one file per tracked issue
├── project_description.md
├── architecture_design.md
└── analyzer_snapshot.json    # repo intelligence cache
```

No database. No cloud sync. Everything is plain text on your machine.

---

## Configuration

```bash
# Set GitHub repo (required for GitHub mode)
echo "GITHUB_REPO=owner/repo" > hub_agents/.env

# Or pass during setup
/github_planner:setup
```

Authentication uses the GitHub CLI (`gh auth login`) or a `GITHUB_TOKEN` environment variable.

---

## Requirements

- Python 3.10+
- Claude Code (any recent version)
- GitHub CLI (`gh`) for GitHub features — optional, `GITHUB_TOKEN` works too
