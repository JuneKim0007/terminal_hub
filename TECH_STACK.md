# Tech Stack

A reference document covering the libraries, APIs, and design decisions behind terminal_hub.
Updated as the project evolves.

---

## What terminal_hub Does

terminal_hub is a locally-run MCP server that connects to Claude Code. It automates the design and planning phase of a project — tracking conversations, creating GitHub issues, and maintaining living project documents — so users can skip the overhead and get straight to building.

---

## Core Language

**Python 3.10+**

- Runs on every major OS without compilation
- Rich ecosystem for CLI tooling, HTTP, and AI APIs
- Simple install via `pip` — no build step required
- Docker-friendly for edge cases and non-standard environments

---

## APIs

### Anthropic Claude API
**Role:** The intelligence layer — generates issue titles, descriptions, architecture summaries, and project documentation from conversation context.

**Why Claude specifically:**
terminal_hub is designed for Claude Code users. Using the same model the user is already talking to keeps behavior consistent and removes the need for a second API key or provider config.

**Library:** `anthropic` (official Python SDK)

---

### GitHub REST API
**Role:** Creates issues, fetches repo info, and manages repository setup (create repo, set remote).

**Why REST over GraphQL:**
REST endpoints cover everything needed for v0.1 and are simpler to implement and debug. GraphQL will be considered if batching becomes a bottleneck in later versions.

**Auth:** Personal access token via `GITHUB_TOKEN` environment variable.
Repo auto-detected from `git remote get-url origin`, overridable via `GITHUB_REPO=owner/repo`.

**Library:** `httpx` (async-capable HTTP client, works well with both sync and async Python)

---

## Workspace Setup

Workspace setup (choosing Local / New Repo / Connect Repo) is handled entirely inside the Claude Code conversation via a dedicated `setup_workspace` MCP tool. When Claude detects no `.terminal_hub/config.yaml` exists, it calls `setup_workspace` with the user's chosen mode and optional repo info.

There is no separate terminal UI process, no `questionary` dependency, and no separate `terminal-hub-setup` command. Claude presents the options as plain text in conversation and the user replies — matching how Claude Code hooks work natively.

---

## MCP Server

### FastMCP / mcp (official Python SDK)
**Role:** Exposes terminal_hub tools to Claude Code via the Model Context Protocol.

Claude Code connects to the server at startup. The server registers tools (`create_issue`, `list_issues`, etc.) that Claude can call during any conversation.

**Confirmation gate:** Tools that write to GitHub require explicit user approval via Claude Code's built-in MCP approval prompt — a single y/n step, no separate question from Claude.

---

## Local Storage

No database. All project context is stored as plain Markdown files inside the project repo:

```
.terminal_hub/
├── config.yaml               — workspace mode and repo settings
├── project_description.md    — what the project does and its goals
├── architecture_design.md    — high-level design decisions
└── issues/
    └── <slug>.md             — one file per tracked issue
```

**Why plain files:**
- Zero setup — no database install or migration
- Human-readable and editable
- Git-friendly — teams can commit `.terminal_hub/` and share context
- Token-efficient — Claude loads only the files it needs, not the full conversation history

Issue files use YAML front matter for structured metadata (title, GitHub URL, date, assignees, labels) and Markdown body for full context.

---

## OS & Environment Coverage

| Environment | Status |
|-------------|--------|
| macOS | Fully supported |
| Linux | Fully supported |
| Windows (cmd / PowerShell) | Supported |
| Windows WSL | Supported (treated as Linux) |
| Docker | Supported in TTY mode (`docker run -it`) |

---

## Workspace Modes

terminal_hub supports three modes, selected at first run via the keyboard menu:

| Mode | GitHub Required | Description |
|------|----------------|-------------|
| **Local** | No | Plans and issues stored on disk only |
| **New Repo** | Yes | Creates a new GitHub repo and links it |
| **Connect Repo** | Yes | Links to an existing GitHub repo |

Mode is saved to `.terminal_hub/config.yaml` and persists across sessions.

---

## Key Design Rationale

**Compatibility over features**
Every library choice prioritises working correctly on Windows, macOS, and Linux out of the box. No platform-specific install steps.

**Local-first**
Everything runs on the user's machine. No cloud sync, no server, no account beyond GitHub and Anthropic API keys. Users stay in control of their data.

**Minimal dependencies**
The install surface is kept small to reduce breakage and keep `pip install terminal-hub` fast and reliable.

**Plain text as the data layer**
Markdown files are universally readable, diff-friendly, and require no tooling to inspect or edit. They also serve as a cheap context-reload mechanism — Claude reads a single `.md` file instead of replaying a full conversation.

**Claude-native**
terminal_hub is not a generic GitHub CLI wrapper. It is designed specifically for Claude Code workflows. The Anthropic API is the only LLM provider, and the MCP server is the only integration surface.
