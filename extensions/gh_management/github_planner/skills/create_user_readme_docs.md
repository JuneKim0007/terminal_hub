---
name: create-user-readme-docs
description: Rules for writing user-facing documentation — README.md, QUICKSTART.md, and docs/user/* pages. Specifies which local files to read first (pyproject.toml, plugin manifests, __main__.py), the medium-project README structure for terminal-hub, badge conventions, and GitHub navigation layout. Load when a user asks to write or update user docs.
alwaysApply: false
triggers:
  - write readme
  - update readme
  - user documentation
  - docs for users
  - README.md
  - quickstart
---

# create-user-readme-docs Skill

Rules for writing user-facing documentation for terminal-hub.

## When to Use

- User asks to write or update `README.md`, `QUICKSTART.md`, or `docs/user/` pages
- User asks for "docs for users", "usage docs", or "how do I document this for end users"
- Any end-user-facing documentation work

## When NOT to Use

- Writing `CONTRIBUTING.md`, architecture docs, or developer/plugin-author docs → use `create-dev-readme-docs` skill instead
- Writing skill files themselves → use `create-skill` skill

---

## Section 2 — Local Files to Read (ordered, with what to extract)

Always read in this priority order before writing any user doc:

### Priority 1 — Project identity (always read first)
```
pyproject.toml
  → name: "terminal-hub"
  → version: "0.2.0"
  → description: "GitHub issue tracking and project context management for Claude Code via MCP"
  → requires-python: ">=3.10"
  → dependencies: mcp>=1.0.0, httpx>=0.27.0, pyyaml>=6.0
  → entry_point: "terminal-hub = terminal_hub.__main__:main"
  → license: MIT
  → PyPI: https://pypi.org/project/terminal-hub/
```

### Priority 2 — User-facing commands and features
```
terminal_hub/__main__.py
  → CLI subcommands:
      terminal-hub install  → "Register terminal-hub in ~/.claude.json (run once)"
      terminal-hub verify   → "Check that terminal-hub is registered in ~/.claude.json"
  → Default (no subcommand): runs MCP server on stdio

extensions/gh_management/github_planner/description.json
  → entry: /th:gh-plan ("let's plan", "plan some work", "github planner")
  → subcommands:
      /th:gh-plan-list      — "list issues", "what's open"
      /th:gh-plan-create    — "create an issue", "draft an issue", "log a bug"
      /th:gh-plan-analyze   — "analyze my repo", "read the codebase"
      /th:gh-plan-setup     — "set up github", "configure the repo", "initialise terminal-hub"
      /th:gh-plan-auth      — "fix auth", "github login"
      /th:gh-plan-unload    — "unload", "clear cache", "free memory"
      /th:gh-plan-settings  — "planner settings", "planning preferences"
      /th:current-stat      — "status", "what's loaded"

extensions/gh_management/gh_implementation/description.json
  → entry: /th:gh-implementation ("implement this issue", "work on an issue", "let's implement")
  → subcommands:
      /th:gh-implementation/implement        — "implement issue", "work on issue"

Command files in commands/ (for full slash command list):
  extensions/gh_management/github_planner/commands/:
    gh-plan.md, gh-plan-list.md, gh-plan-create.md, gh-plan-analyze.md,
    gh-plan-setup.md, gh-plan-auth.md, gh-plan-unload.md, gh-plan-settings.md,
    current-stat.md
  extensions/gh_management/gh_implementation/commands/:
    gh-implementation.md
```

### Priority 3 — Existing docs to update (not replace)
```
README.md         → read current structure; do not duplicate existing content
QUICKSTART.md     → read existing steps; extend not rewrite
hub_agents/hub_agents/extensions/gh_planner/project_summary.md
                  → project goals and tech stack (if exists)
```

---

## Section 3 — README Structure for terminal-hub (medium, MCP server + CLI tool)

terminal-hub is a **medium project** (Python CLI + MCP server, 2 active plugins, ~10 slash commands). Apply this 11-section structure:

```
1. # terminal-hub  ← H1 with badges inline (see Section 6 for badge template)

2. [1–2 sentence description]
   "terminal-hub is an MCP server for Claude Code that gives it GitHub issue planning,
   tracking, and implementation capabilities via slash commands."

3. ## Features  ← bullet list, one line per capability, verb-first
   - Plan issues — describe a feature in plain English, Claude expands it into a labelled GitHub issue
   - Track work locally — issues stored as Markdown files in hub_agents/issues/
   - Implement end-to-end — Claude reads the issue, implements, diffs, pushes, and closes it
   - Analyze repo — scan codebase to generate project_summary.md and project_detail.md
   - Milestone management — derive sprint milestones, auto-assign issues
   - Design context — extract and apply design principles from project docs during planning

4. ## Requirements
   - Python 3.10+
   - Claude Code (claude.ai/code)
   - A git repository (GitHub account optional — local-only mode supported)

5. ## Installation
   pip install terminal-hub
   terminal-hub install

6. ## Quick Start  ← minimal working example (3–5 steps, bash code blocks)
   1. pip install terminal-hub && terminal-hub install
   2. Open Claude Code in your project directory
   3. Say: "let's plan" or "/th:gh-plan" to start the planner
   4. Describe a feature — Claude drafts and submits the issue
   5. Say "implement this issue" — Claude picks it up, codes, pushes, closes

7. ## Slash Commands Reference  ← table with trigger phrases, not just command names
   | Command | Trigger phrase | What it does |
   |---------|---------------|--------------|
   | /th:gh-plan | "let's plan" | Plan and create GitHub issues |
   | /th:gh-plan-list | "list issues" | Show all tracked issues |
   | /th:gh-plan-create | "create an issue" | Draft and submit a single issue |
   | /th:gh-plan-analyze | "analyze my repo" | Scan codebase, generate project docs |
   | /th:gh-plan-setup | "set up github" | First-time setup or reconfigure |
   | /th:gh-plan-auth | "fix auth" | Fix GitHub authentication |
   | /th:gh-implementation | "implement this issue" | Implement a tracked issue end-to-end |
   | /th:current-stat | "status" | Show what's currently loaded |

8. ## Configuration  ← env vars table
   | Variable | Required | Default | Where to set | Description |
   |----------|----------|---------|--------------|-------------|
   | GITHUB_TOKEN | No* | — | hub_agents/.env or shell | GitHub PAT — required for GitHub mode |
   | GITHUB_REPO | No* | — | hub_agents/.env or shell | owner/repo — required for GitHub mode |
   | *Local-only mode works without any env vars. |

9. ## How It Works  ← 2–3 sentences (no code)
   terminal-hub runs as an MCP server alongside Claude Code. It exposes ~55 tools
   that Claude uses to read issues, scan repos, draft plans, and push to GitHub.
   Plugins (gh_management/github_planner and gh_management/gh_implementation) each
   register their own tools via register(mcp) and load their own slash commands.

10. ## Contributing  ← one sentence + link
    See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, plugin authoring, and contribution guidelines.

11. ## License
    MIT — see [LICENSE](LICENSE).
```

---

## Section 4 — docs/ Directory Structure

When writing user docs beyond README, create this layout if absent:

```
docs/
├── user/
│   ├── index.md            ← overview + links to sub-pages
│   ├── installation.md     ← full install + troubleshooting (pip, verify, .env setup)
│   ├── quick-start.md      ← 5-minute tutorial (plan → implement flow)
│   ├── commands.md         ← full slash command reference (one section per command)
│   └── configuration.md    ← all env vars + hub_agents/ workspace layout
```

Link from README.md `## Slash Commands Reference` → `docs/user/commands.md` for full command detail.

---

## Section 5 — Writing Rules

1. **Lead with what the user gets, not how it works internally**
   - Bad:  `"terminal-hub uses FastMCP to register MCP tools via the register(mcp) pattern..."`
   - Good: `"Say 'let's plan' in Claude Code and terminal-hub drafts, labels, and submits a GitHub issue for you."`

2. **Every CLI command must appear in an exact-syntax bash code block**
   - Bad:  `"Run the install command"`
   - Good:
     ```bash
     pip install terminal-hub
     terminal-hub install
     ```

3. **Slash commands must show trigger phrases, not internal command names**
   - Bad:  `"Use /th:gh-plan to start the planner"`
   - Good: `"Say 'let's plan' or 'plan some work' to activate the GitHub planner"`

4. **Configuration table must always include a "Where to set" column**
   - Bad:  `| GITHUB_TOKEN | Required | GitHub PAT |`
   - Good: `| GITHUB_TOKEN | No* | hub_agents/.env or shell env | GitHub Personal Access Token |`

5. **Features list: one line per capability, verb-first**
   - Bad:  `"gh-plan: planning functionality for issues"`
   - Good: `"Plan issues — describe a feature in plain English, get a labelled GitHub issue back"`

6. **Add a Table of Contents if README exceeds 300 lines** (GitHub anchor links):
   ```markdown
   - [Features](#features)
   - [Installation](#installation)
   - [Quick Start](#quick-start)
   ```

7. **Never invent env var names or CLI flags** — only document what exists in `__main__.py`, `plugin.json`, or `description.json`.

---

## Section 6 — Badge Template

```markdown
[![PyPI version](https://img.shields.io/pypi/v/terminal-hub.svg)](https://pypi.org/project/terminal-hub/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen.svg)]()
```

Place badges on the line immediately following the `# terminal-hub` heading.

---

## Section 7 — Before/After Examples

### Example 1: Weak → Strong Features List Entry

**Before (weak):**
```markdown
## Features
- GitHub planning support
- Issue management
- Implementation helper
```

**After (strong):**
```markdown
## Features

- **Plan issues** — describe a feature in plain English; Claude expands it into a labelled, milestoned GitHub issue
- **Track locally** — issues stored as `hub_agents/issues/*.md` files — no GitHub auth needed for local mode
- **Implement end-to-end** — Claude reads the issue, implements the change, shows a diff, pushes, and closes it
- **Analyze your repo** — scan the codebase to generate `project_summary.md` (goals + design principles) and `project_detail.md` (per-feature specs)
- **Milestone management** — derive sprint milestones from feature scope, auto-assign issues silently
```

### Example 2: Bare Install → Contextual Install with Code Block

**Before (bare):**
```markdown
## Installation
Install the package and run install.
```

**After (contextual):**
```markdown
## Installation

**Requirements:** Python 3.10+, Claude Code

```bash
pip install terminal-hub
terminal-hub install   # registers terminal-hub in ~/.claude.json
```

Verify the installation:
```bash
terminal-hub verify
```

Then open Claude Code in any project directory — terminal-hub is ready.
```

### Example 3: Missing Configuration Table → Complete Table

**Before (missing):**
```markdown
## Configuration
Set GITHUB_TOKEN and GITHUB_REPO to use GitHub features.
```

**After (complete table):**
```markdown
## Configuration

terminal-hub works in **local-only mode** (no env vars needed) or **GitHub mode**:

| Variable | Required | Where to set | Description |
|----------|----------|--------------|-------------|
| `GITHUB_TOKEN` | GitHub mode only | `hub_agents/.env` or shell | GitHub Personal Access Token with `repo` scope |
| `GITHUB_REPO` | GitHub mode only | `hub_agents/.env` or shell | Target repo in `owner/repo` format (e.g. `alice/my-project`) |

**hub_agents/.env** (created by `terminal-hub install`):
```
GITHUB_TOKEN=ghp_...
GITHUB_REPO=alice/my-project
```
```
