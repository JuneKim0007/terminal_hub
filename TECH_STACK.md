# Tech Stack

A reference document covering the libraries, design decisions, and architecture of terminal-hub.

---

## What terminal-hub does

terminal-hub is an **extensible plugin framework for Claude Code**. It pairs an MCP server (tool API) with Claude slash commands (conversational workflow prompts) so teams can build, share, and compose workflow plugins without touching the core server.

The **github_planner** plugin ships as the reference implementation — a full GitHub issue management workflow built using the plugin framework.

---

## Architecture

```
terminal_hub/            ← core framework
├── server.py            ← FastMCP setup, plugin loader loop, core tools
├── plugin_loader.py     ← discovers extensions/*/plugin.json, calls register(mcp)
├── extension_loader.py  ← extension registry helpers
├── workspace.py         ← resolves PROJECT_ROOT or cwd
├── config.py            ← hub_agents/config.yaml (mode, repo)
├── env_store.py         ← hub_agents/.env (GITHUB_REPO, GITHUB_TOKEN)
├── install.py           ← CLI: copies commands to ~/.claude/commands/<plugin>/
├── errors.py            ← centralised error messages (error_msg.json)
├── slugify.py           ← URL-safe slug generation
└── platform_runner.py   ← OS detection + subprocess runner for extensions

extensions/              ← bundled extensions (shipped with package)
├── github_planner/      ← reference implementation
│   ├── __init__.py      ← register(mcp) entry point + all tool implementations
│   ├── client.py        ← GitHub REST API client (httpx)
│   ├── storage.py       ← issue file I/O (hub_agents/issues/<slug>.md)
│   ├── auth.py          ← token resolution (env → gh CLI → none)
│   ├── analyzer.py      ← repo intelligence: snapshot I/O + summarize_for_prompt
│   ├── default.analyzer.json  ← analyzer descriptor (owned paths, TTL)
│   ├── prompt_debugger.json   ← inspect tool descriptor (tracked item paths)
│   └── commands/        ← slash command prompts for this extension
│       └── github-planner/  ← sub-commands (analyze, create-issue, unload, …)
├── plugin_creator/      ← conversational plugin scaffolding extension
└── command_config.json          ← global extension runner registry (framework-level)

extensions/builtin/      ← framework-level slash commands (help.md, inspect.md)
AGENT_WORKFLOW.md        ← agent execution guide for cleanup/refactor tasks
```

Both layers are required for a complete workflow:
- MCP tools handle data, APIs, and file I/O
- Slash commands handle conversation, confirmation, and user interaction

---

## Core Language

**Python 3.10+**

- Runs on every major OS without compilation
- Rich ecosystem for CLI tooling, HTTP, and AI integration
- Simple install via `pip` — no build step
- `|` union type syntax (used throughout) requires 3.10+

---

## MCP Server

**FastMCP** (`mcp` package — official Python SDK)

Claude Code connects to the server at startup via stdio. The server registers tools dynamically by discovering `plugins/*/plugin.json` and calling each plugin's `register(mcp)` function. Adding a plugin requires no changes to core server code.

**Plugin contract:**
- `plugin.json` — manifest with name, version, entry module, slash command list, conversation triggers
- `register(mcp)` — registers `@mcp.tool()` decorated functions with FastMCP
- `commands/*.md` — slash command prompts installed to `~/.claude/commands/<plugin>/`

---

## GitHub Integration

**httpx** — async-capable HTTP client for GitHub REST API calls

Why REST over GraphQL: REST endpoints cover all needed operations and are simpler to debug. All GitHub API calls go through `plugins/github_planner/client.py` — the core framework has no GitHub dependency.

**Auth resolution order:**
1. `GITHUB_TOKEN` environment variable
2. `gh auth token` (GitHub CLI)
3. None — local-only mode

---

## Local Storage

No database. All state is plain files in `hub_agents/`:

| File | Content |
|------|---------|
| `config.yaml` | Workspace mode (local/github) and repo |
| `.env` | GITHUB_REPO, optional GITHUB_TOKEN |
| `issues/<slug>.md` | Issue drafts with YAML front matter + Markdown body |
| `extensions/gh_planner/project_summary.md` | Global rules: tech stack, design principles, pitfalls (≤500 tokens) |
| `extensions/gh_planner/project_detail.md` | Feature-area design dictionary (H2 sections, loaded per-section) |
| `extensions/gh_planner/analyzer_snapshot.json` | GitHub metadata cache (labels, assignees, issue patterns) |
| `extensions/gh_planner/file_hashes.json` | Git blob SHAs for incremental `analyze_repo_full` |
| `extensions/gh_planner/file_tree.json` | Local filesystem tree cache (TTL: 1h) |

**Why plain files:**
- Zero setup — no database or migration
- Human-readable and editable
- Git-friendly (teams can commit `hub_agents/` if desired)
- Token-efficient — Claude loads only the files it needs

---

## OS Coverage

| Environment | Status |
|-------------|--------|
| macOS | Fully supported |
| Linux (Ubuntu, Fedora, Arch, Alpine) | Fully supported |
| Windows (cmd / PowerShell) | Supported |
| Windows WSL | Supported (treated as Linux) |

---

## Key Design Rationale

**Plugin-first**
The core framework has no opinion about what workflow you run. GitHub issue management is one example. Teams can add plugins for Jira, Linear, Notion, or internal tools by dropping a folder into `plugins/` — no core changes required.

**Conversation is the workflow**
MCP tools provide data; slash commands provide the conversational interface. Neither is sufficient alone. The `.md` files are first-class citizens, not documentation — they define how Claude behaves during a workflow session.

**Local-first**
Everything runs on the user's machine. No cloud sync, no server, no account beyond GitHub and optional API keys. Users stay in control of their data.

**Minimal dependencies**
The install surface is kept small: `mcp` (FastMCP), `httpx` (HTTP), `pyyaml` (config). No framework bloat.

**Token-efficient caching**
The analyzer snapshot stores pre-computed aggregates (label frequency, body section ratios, title prefixes) — not raw issue bodies. `summarize_for_prompt()` converts the snapshot to a ~80-token one-liner for injection into slash command prompts.

**Honest MCP limitations**
terminal-hub does not pretend to have capabilities it lacks. The prompt debugger (`/terminal_hub:inspect`) reports disk state and Claude self-reports what it has read — it does not claim to read the context window directly.
