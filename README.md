# terminal-hub

An extensible MCP server for Claude Code that pairs Python tools with conversational slash commands. Manages GitHub issues, plans features, and maintains persistent project context — all through natural conversation.

Ships with **github_planner** (issue management + repo analysis) and **plugin_creator** (conversational plugin scaffolding) as reference extensions.

---

## How it works

terminal-hub runs as an MCP server. Extensions register two things:

- **MCP tools** — Python functions Claude can call (fetch data, write files, call APIs)
- **Slash commands** — Markdown prompt files that drive the conversational workflow

The server handles data; the commands handle conversation. Together they form complete, self-contained workflows.

---

## Quick start

```bash
pip install terminal-hub
terminal-hub install    # registers MCP server + installs slash commands
# restart Claude Code
```

Then in Claude Code:
```
/t-h:github-planner
```

---

## Bundled extension: github_planner

Full GitHub issue lifecycle management with project context awareness.

| Command | What it does |
|---------|-------------|
| `/t-h:github-planner` | Integrated flow — setup → analysis → planning → issue creation |
| `/t-h:github-planner/create-issue` | Single guided issue with project context lookup |
| `/t-h:github-planner/analyze` | Build feature-area design dictionary from repo structure |
| `/t-h:github-planner/list-issues` | Show tracked issues |
| `/t-h:github-planner/setup` | Configure workspace and GitHub repo |
| `/t-h:github-planner/auth` | Auth recovery flow |

### Project context

After analysis, terminal-hub maintains two docs in `hub_agents/extensions/gh_planner/`:

- **`project_summary.md`** — Global rules: tech stack, design principles, known pitfalls (≤500 tokens, loaded on every planning session)
- **`project_detail.md`** — Feature-area design dictionary: one H2 section per feature with "Existing Design" + "Extension Guidelines". Retrieved section-by-section via `lookup_feature_section(feature="X")` — never loaded in full.

When creating issues, Claude automatically calls `lookup_feature_section` to ground acceptance criteria in the existing design. New repos (no docs) skip the lookup gracefully.

---

## Bundled extension: plugin_creator

Conversational plugin scaffolding — generates `plugin.json`, `__init__.py`, `description.json`, command files, and a test scaffold.

```
/t-h:create-plugin
```

---

## Writing an extension

1. Create `extensions/<name>/` with `plugin.json`, `description.json`, and `__init__.py`
2. In `__init__.py`, implement `register(mcp)` and decorate tools with `@mcp.tool()`
3. Add command `.md` files to `extensions/<name>/commands/`
4. Re-install to copy commands: `terminal-hub install`

```python
# extensions/my_ext/__init__.py
def register(mcp) -> None:
    @mcp.tool()
    def my_tool(input: str) -> dict:
        """Does something useful."""
        return {"result": input.upper(), "_display": f"Done: {input.upper()}"}
```

```json
// extensions/my_ext/plugin.json
{
  "name": "my_ext",
  "version": "0.1.0",
  "description": "My custom workflow extension",
  "entry": "extensions.my_ext",
  "install_namespace": "t-h",
  "entry_command": "start.md",
  "commands_dir": "commands",
  "commands": ["start.md"]
}
```

Use `/t-h:create-plugin` for guided scaffolding.

---

## Local state

All terminal-hub state lives in `hub_agents/` (gitignored):

```
hub_agents/
├── .env                                 # GITHUB_REPO, optional GITHUB_TOKEN
├── config.yaml                          # mode: local|github, repo: owner/repo
├── analyzer_snapshot.json               # repo intelligence cache (labels, assignees)
├── issues/
│   └── <slug>.md                        # YAML front matter + body per issue
└── extensions/gh_planner/
    ├── project_summary.md               # global rules and tech overview
    └── project_detail.md                # feature-area design dictionary
```

No database. No cloud sync. Everything is plain text.

---

## Configuration

```bash
# Set GitHub repo (required for GitHub mode)
echo "GITHUB_REPO=owner/repo" > hub_agents/.env
```

Authentication uses the GitHub CLI (`gh auth login`) or `GITHUB_TOKEN` env var.

---

## Requirements

- Python 3.10+
- Claude Code
- GitHub CLI (`gh`) for GitHub features — or set `GITHUB_TOKEN`
