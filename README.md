# terminal_hub

A Python MCP server that integrates with Claude Code to automate GitHub issue creation and maintain living project context documents — so you can focus on building instead of bookkeeping.

---

## How it works

You have a planning conversation with Claude. As features and tasks come up, Claude calls `create_issue` directly (with your confirmation via the MCP approval prompt). Issues are created on GitHub and a local `.md` file is written inside your project for future context reloading.

No separate terminal UI. No manual copy-pasting. The conversation *is* the workflow.

---

## Quick start

### 1. Install

```bash
pip install -e /path/to/terminal_hub
```

Or from GitHub:

```bash
pip install git+https://github.com/JuneKim0007/terminal_hub.git
```

### 2. Auth

You need one of these — terminal_hub checks in this order:

| Method | How |
|---|---|
| **GitHub CLI** (recommended) | `gh auth login` — zero config after that |
| **Personal Access Token** | Set `GITHUB_TOKEN=your_token` in your MCP env config |

If neither is found, Claude will present both options and walk you through login interactively.

### 3. Add to Claude Code MCP config

Open your Claude Code MCP settings and add:

```json
{
  "mcpServers": {
    "terminal-hub": {
      "command": "python",
      "args": ["-m", "terminal_hub"],
      "env": {
        "GITHUB_REPO": "owner/your-repo"
      }
    }
  }
}
```

`GITHUB_REPO` is optional — if omitted, terminal_hub auto-detects the repo from your `git remote` origin.

### 4. Start a session

Open Claude Code in your project directory. Claude will:
1. Auto-initialize `.terminal_hub/` on first run
2. Call `get_setup_status` to check if the workspace is configured
3. If not configured, present options and call `setup_workspace` with your choice

---

## Workspace modes

| Mode | What it does |
|---|---|
| `local` | Track plans and issues on this machine only — no GitHub needed |
| `github` | Create a new GitHub repository and start tracking |
| `connect` | Link to an existing GitHub repository |

---

## MCP Tools reference

### Auth

| Tool | When Claude calls it |
|---|---|
| `check_auth` | Whenever a GitHub call returns an auth error |
| `verify_auth` | After you run `gh auth login` to confirm it worked |

### Issues

| Tool | What it does |
|---|---|
| `create_issue` | Creates a GitHub issue and writes a local `.md` file |
| `list_issues` | Returns all tracked issues from `.terminal_hub/issues/` |
| `get_issue_context` | Reads a single issue file by slug — cheap context reload |

### Project context

| Tool | What it does |
|---|---|
| `update_project_description` | Overwrites `.terminal_hub/project_description.md` |
| `update_architecture` | Overwrites `.terminal_hub/architecture_design.md` |
| `get_project_context` | Reads one or both context docs |

### Workspace setup

| Tool | What it does |
|---|---|
| `get_setup_status` | Returns config status + options if not configured |
| `setup_workspace` | Saves workspace mode and optional repo to config |

---

## Local file layout

```
your-project/
└── .terminal_hub/
    ├── config.yaml               # workspace mode + repo
    ├── project_description.md    # living project description
    ├── architecture_design.md    # living architecture doc
    └── issues/
        ├── fix-auth-bug.md       # one file per issue
        └── add-dark-mode.md
```

Each issue file uses YAML front matter:

```markdown
---
title: Fix auth bug
issue_number: 42
github_url: https://github.com/owner/repo/issues/42
created_at: "2026-03-16"
assignees: []
labels: [bug]
---

## Overview
Fix the login flow...
```

---

## Running tests

```bash
pip install pytest pytest-cov
pytest
```

Coverage gate is set at 80%. Current coverage: **100%** across all modules.

---

## Project structure

```
terminal_hub/
├── server.py          # FastMCP server — all 10 tools registered here
├── auth.py            # Token resolution: env → gh CLI → present options
├── github_client.py   # GitHub REST API via httpx, AI-friendly errors
├── storage.py         # Read/write issue .md files and context docs
├── workspace.py       # Auto-init .terminal_hub/, detect git remote
├── config.py          # Read/write .terminal_hub/config.yaml
├── slugify.py         # Issue title → kebab-case filename
└── prompts.py         # System prompt delivered to Claude via MCP prompt
```

---

## Error handling

Every error returned by a tool is a structured dict Claude can act on:

```json
{
  "error": "auth_failed",
  "message": "GitHub rejected the token.",
  "suggestion": "Your GITHUB_TOKEN is invalid or expired. Generate a new one at https://github.com/settings/tokens with the 'repo' scope."
}
```

Claude reads the `suggestion` and tells you exactly what to do — no manual debugging.
