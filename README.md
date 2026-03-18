# terminal-hub

An MCP server for Claude Code that pairs Python tools with conversational slash commands. Manages GitHub issues, analyzes repositories, and maintains persistent project context — all through natural conversation.

Ships with **github_planner** (issue management + repo analysis) and **plugin_creator** (conversational plugin scaffolding) as built-in extensions.

---

## The idea

Most GitHub automation tools require you to manually invoke each step. terminal-hub flips this: you describe what you're planning, and the system handles the rest — workspace setup, repo analysis, context loading, issue creation, and cleanup — all in one flow.

---

## Quick start

```bash
pip install terminal-hub
terminal-hub install    # registers MCP server + installs slash commands
# restart Claude Code
```

---

## The integrated flow

```
/th:github-planner
```

**This single command handles everything.** You don't need to call any other command manually. Here's what happens automatically:

1. **Checks your workspace** — sets up GitHub config if first time
2. **Checks project docs** — analyzes your repo if docs are missing or stale (>7 days)
3. **Loads your project context** — silently reads design principles and feature areas
4. **Starts a planning conversation** — "Let me know any plans for this!"
5. **Creates issues** — drafts each one locally, shows a confirmation preview, then pushes to GitHub only after you approve
6. **Updates project docs** — merges new feature areas into your design dictionary
7. **Cleans up on request** — once done, asks if you want to unload all cached data so Claude's context stays lean

> **Context cleanup:** When planning is done, terminal-hub will ask:
> *"Unload cached data to free up context? (yes/no)"*
>
> Saying yes clears all in-memory caches — analysis results, project docs, file trees, session headers — so Claude doesn't accumulate too much context and start making mistakes from prompt overload. Your issues and project docs on disk are always preserved.

---

## What the integrated flow includes

All of the following happen **inside** `/th:github-planner`. You do not need to call them separately:

| What | How |
|------|-----|
| Workspace setup | `setup_workspace` — configures GitHub repo and auth |
| Repo analysis | `analyze_repo_full` → `save_project_docs` — builds your design dictionary |
| Context loading | `get_session_header` + `lookup_feature_section` — loads only what's relevant |
| Issue drafting | `draft_issue` — saves locally with status=pending |
| Confirmation gate | Shows preview of all issues before any GitHub API call |
| Issue submission | `submit_issue` — pushes to GitHub after your explicit approval |
| Workflow scaffolding | `generate_issue_workflows` — appends Agent Workflow + Program Workflow to every issue |
| Doc updates | `update_project_detail_section` — merges new sections without rewriting the whole file |
| Cleanup | `unload_plugin` — clears all caches when you're done |

---

## Sub-commands (for targeted use)

If you only need one specific step, these work independently:

| Command | Say | Does |
|---------|-----|------|
| `/th:github-planner/create-issue` | "create an issue" | Single guided issue with project context lookup |
| `/th:github-planner/analyze` | "analyze my repo" | Build or refresh the design dictionary |
| `/th:github-planner/list-issues` | "list issues" | Show tracked issues as a table |
| `/th:github-planner/setup` | "set up github" | Configure workspace and GitHub repo |
| `/th:github-planner/auth` | "fix auth" | Recover from GitHub auth failures |
| `/th:github-planner/unload` | "unload" | Clear all caches manually |

For most workflows, **just use `/th:github-planner`** — it composes all of these.

---

## Issue structure

Every issue terminal-hub creates gets two workflow sections appended automatically:

**Agent Workflow** — how Claude should execute the task:
- Orient: re-read the issue, identify affected files, understand acceptance criteria
- Plan: list changes, confirm they fit existing patterns
- Implement: atomic, test-verified changes
- Verify: all tests pass, coverage ≥ 80%, criteria met

**Program Workflow** — how the change fits the system:
- Change type (feature / bug / refactor — inferred from labels)
- Affected components
- Test plan checklist

Each issue becomes a self-contained unit of work that an agent can pick up and execute without needing additional context from you.

---

## Project context (how memory works)

After analysis, terminal-hub maintains two files in `hub_agents/extensions/gh_planner/`:

**`project_summary.md`** (≤500 tokens) — loaded at the start of every planning session:
- Tech stack, implemented features, design principles, known pitfalls

**`project_detail.md`** — feature-area design dictionary, never loaded in full:
- One H2 section per feature area (e.g. "Auth", "Issue Management", "Plugin Framework")
- Each section: Existing Design + Extension Guidelines
- Loaded section-by-section via `lookup_feature_section(feature="X")` only when relevant to the current task

This means Claude references exactly what it needs and ignores everything else — no prompt overload, no confusion from stale or irrelevant context.

---

## Plugin creator

```
/th:create-plugin
```

Conversational plugin scaffolding. Generates `plugin.json`, `__init__.py`, `description.json`, command files, and a test scaffold — one step at a time, with your input at each stage.

---

## Writing an extension

1. Create `extensions/<name>/` with `plugin.json`, `description.json`, and `__init__.py`
2. Implement `register(mcp)` and decorate tools with `@mcp.tool()`
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
  "entry_command": "start.md",
  "commands_dir": "commands",
  "commands": ["start.md"]
}
```

No `install_namespace` needed — extensions inherit the global `th` prefix automatically. Set it only if you want a different prefix for a specific plugin.

Use `/th:create-plugin` for guided scaffolding.

---

## Slash command namespace

All commands use the `th` prefix. This is controlled by a single file:

```python
# terminal_hub/namespace.py
COMMAND_NAMESPACE = "th"
```

Changing this value and re-running `terminal-hub install` renames all slash commands system-wide. No other Python file needs editing.

> **Note on description.json:** Command strings inside `description.json` files (e.g. `"/th:github-planner"`) are informational labels the MCP server uses to suggest commands to Claude. They are static JSON — JSON has no import mechanism, so these strings cannot be derived from `namespace.py` automatically. The actual slash command prefix is determined by the installed directory name, not these strings. If you change `COMMAND_NAMESPACE`, update `description.json` strings for consistency, but the commands will work correctly regardless.

---

## Local state

All terminal-hub state lives in `hub_agents/` (gitignored by default):

```
hub_agents/
├── .env                                 # GITHUB_REPO, optional GITHUB_TOKEN
├── config.yaml                          # mode: local|github
├── analyzer_snapshot.json               # repo intelligence cache (labels, assignees)
├── issues/
│   └── <slug>.md                        # YAML front matter + body per issue
└── extensions/gh_planner/
    ├── project_summary.md               # global rules and tech overview (≤500 tokens)
    └── project_detail.md                # feature-area design dictionary
```

No database. No cloud sync. Everything is plain text. Delete `hub_agents/` at any time to start fresh — terminal-hub will rebuild on next use.

---

## Authentication

```bash
gh auth login          # recommended — terminal-hub detects this automatically
# or
export GITHUB_TOKEN=ghp_...
```

---

## Requirements

- Python 3.10+
- Claude Code
- GitHub CLI (`gh`) for GitHub features — or set `GITHUB_TOKEN`
