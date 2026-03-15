# terminal_hub — Design Spec

**Date:** 2026-03-15
**Status:** Approved

---

## Overview

`terminal_hub` is a locally-installed MCP server that integrates with Claude Code to automate GitHub issue creation and project planning. During planning conversations, Claude tracks context, suggests creating GitHub issues in real-time with a y/n confirmation prompt, and continuously maintains a set of local markdown files that serve as lightweight project memory.

---

## Problem Statement

Developers lose momentum switching between Claude Code and GitHub's web UI to create and track issues during planning sessions. There is no native way for Claude Code to automatically capture planning decisions as GitHub issues, nor to maintain a persistent, token-efficient local record of project context across sessions.

---

## Architecture

`terminal_hub` runs as a local MCP server process. Claude Code connects to it at startup via the MCP protocol. The server communicates outbound to the GitHub REST API and reads/writes a `.terminal_hub/` directory inside the user's active project repo.

```
Claude Code
    │
    ▼
terminal_hub (MCP server, runs locally via Python)
    ├── GitHub REST API  (create issues, fetch repo info)
    └── .terminal_hub/  (local project context files)
         ├── project_description.md
         ├── architecture_design.md
         └── issues/
              ├── fix-auth-bug.md
              └── add-login-page.md
```

**Language:** Python
**Distribution:** PyPI (`pip install terminal-hub`)
**GitHub auth:** Personal access token via `GITHUB_TOKEN` environment variable
**Repo targeting:** Determined automatically from `git remote get-url origin` in the working directory. Overridable via `GITHUB_REPO` env var (format: `owner/repo`).
**Working directory:** The server uses the `cwd` of the Claude Code process that started it. Each Claude Code session operates in its own project directory, so multi-project use is naturally isolated.

---

## Server Startup Behavior

On startup, the MCP server:
1. Resolves the working directory from `cwd`
2. Detects the GitHub repo from `git remote get-url origin` (or `GITHUB_REPO` env var)
3. Automatically creates `.terminal_hub/` structure if it does not exist (equivalent to `init`) — no user action required

This means `init` is implicit and always runs at server start. It is idempotent and safe to re-run.

**Startup failure modes:**
- If `git remote get-url origin` fails (not a git repo, or no remote set) and `GITHUB_REPO` is not set: the server starts in **read-only mode**. GitHub tools (`create_issue`) return an error: `"No GitHub repo detected. Set GITHUB_REPO=owner/repo or run from a git repo with a remote."` Local file tools (`list_issues`, `get_issue_context`, `update_project_description`, `update_architecture`) continue to work normally.
- If `GITHUB_TOKEN` is missing: the server starts in **read-only mode** with the same behavior — local tools work, `create_issue` returns an error: `"GITHUB_TOKEN is not set. Set it in your MCP config env."`
- If `GITHUB_TOKEN` is set but invalid: `create_issue` fails at call time with the GitHub API error message passed through to Claude.

---

## MCP Tools

### Tool Schemas

#### `create_issue`
Creates a GitHub issue and writes a local context file.

**Requires user confirmation:** Yes (via Claude Code MCP approval prompt — this is the single canonical confirmation gate. Claude does NOT ask a separate natural language question before calling this tool; the MCP approval prompt is the y/n the user sees.)

**Input:**
```json
{
  "title": "string (required) — issue title",
  "body": "string (required) — full issue description in markdown",
  "labels": "array of strings (optional) — GitHub label names",
  "assignees": "array of strings (optional) — GitHub usernames"
}
```

**Behavior:**
- POSTs to GitHub Issues API
- Derives filename slug from `title` using this normalization: lowercase → strip all non-alphanumeric characters except spaces → replace spaces with hyphens → collapse consecutive hyphens → truncate at 60 characters → strip trailing hyphens. Example: "Fix auth bug!" → `fix-auth-bug`.
- Slug collision is checked against the filesystem (not in-memory). If `.terminal_hub/issues/<slug>.md` already exists (whether created by `create_issue` or manually by the user), appends a numeric suffix: `fix-auth-bug-2.md`, `fix-auth-bug-3.md`, etc.
- Writes `.terminal_hub/issues/<slug>.md` with: title, GitHub issue URL, body, creation date, assignees, and labels

**Returns (success):**
```json
{
  "issue_number": 42,
  "url": "https://github.com/owner/repo/issues/42",
  "local_file": ".terminal_hub/issues/fix-auth-bug-2.md"
}
```
Note: `local_file` reflects the actual resolved filename after collision handling — it may differ from the base slug.

**Returns (partial failure — GitHub issue created but local file write failed):**
```json
{
  "issue_number": 42,
  "url": "https://github.com/owner/repo/issues/42",
  "local_file": null,
  "warning": "local_write_failed",
  "warning_message": "Issue created on GitHub but local file could not be written: ..."
}
```

**Returns (error — read-only mode or API failure):**
```json
{
  "error": "github_unavailable",
  "message": "..."
}
```

---

#### `update_project_description`
Updates `.terminal_hub/project_description.md` based on current conversation context.

**Requires user confirmation:** No

**Input:**
```json
{
  "content": "string (required) — full markdown content to write"
}
```

**Behavior:** Overwrites the file. Claude must call `get_project_context` with `"file": "project_description"` before calling this tool to retrieve existing content and preserve or extend it.

**Returns (success):**
```json
{ "updated": true, "file": ".terminal_hub/project_description.md" }
```

**Returns (error):**
```json
{ "error": "write_failed", "message": "..." }
```

---

#### `update_architecture`
Updates `.terminal_hub/architecture_design.md`.

**Requires user confirmation:** No

**Input:**
```json
{
  "content": "string (required) — full markdown content to write"
}
```

**Behavior:** Overwrites the file. Claude must call `get_project_context` with `"file": "architecture"` before calling this tool to retrieve existing content and preserve or extend it.

**Returns (success):**
```json
{ "updated": true, "file": ".terminal_hub/architecture_design.md" }
```

**Returns (error):**
```json
{ "error": "write_failed", "message": "..." }
```

---

#### `list_issues`
Returns all tracked issues for Claude's context.

**Requires user confirmation:** No

**Input:** None

**Behavior:**
- Reads all `.md` files in `.terminal_hub/issues/`
- Parses the YAML front matter block (between `---` delimiters) from each file to extract metadata. Body content below the front matter is excluded from this response.
- Returns local metadata only (no live GitHub API call) to keep it fast and token-efficient
- Results are sorted by `created_at` descending (most recent first)
- `created_at` is stored and parsed as `YYYY-MM-DD` (UTC date, no time component)

**Returns:**
```json
{
  "issues": [
    {
      "slug": "fix-auth-bug",
      "title": "Fix auth bug",
      "issue_number": 42,
      "github_url": "https://github.com/owner/repo/issues/42",
      "created_at": "2026-03-15",
      "assignees": [],
      "labels": [],
      "file": ".terminal_hub/issues/fix-auth-bug.md"
    }
  ]
}
```

---

#### `get_project_context`
Reads `project_description.md` and/or `architecture_design.md` so Claude can preserve their content before overwriting.

**Requires user confirmation:** No

**Input:**
```json
{
  "file": "string (required) — one of: 'project_description', 'architecture', 'all'"
}
```
Use `"all"` to fetch both files in a single call (returns both in the response). This is the expected pattern before calling both `update_project_description` and `update_architecture` in sequence.

**Returns (success — single file):**
```json
{
  "file": "project_description",
  "content": "...full markdown content..."
}
```

**Returns (success — `"all"`):**
```json
{
  "project_description": "...content...",
  "architecture": null
}
```
Fields are `null` when the corresponding file does not yet exist.

**Returns (not found — file does not exist yet):**
```json
{
  "file": "project_description",
  "content": null
}
```

---

#### `get_issue_context`
Reads a specific issue file to cheaply reload context in future sessions.

**Requires user confirmation:** No

**Input:**
```json
{
  "slug": "string (required) — issue filename without .md extension (e.g. fix-auth-bug)"
}
```

**Returns (success):**
```json
{
  "slug": "fix-auth-bug",
  "content": "...full markdown content of the file..."
}
```

**Returns (not found):**
```json
{
  "error": "not_found",
  "message": "No issue file found for slug 'fix-auth-bug'. Use list_issues to see available slugs."
}
```

---

## System Prompt (Bundled in Server)

The system prompt is delivered via the MCP `prompts/list` endpoint as a named prompt `terminal_hub_instructions`. Claude Code does **not** auto-inject MCP prompts — users must invoke it manually with `/mcp terminal-hub terminal_hub_instructions` at the start of a planning session, or it can be included in a project-level `CLAUDE.md` file.

The user workflow (step 4) should note this. The server also embeds a brief instruction in each tool's `description` field reminding Claude to check `terminal_hub_instructions` if it has not done so.

The following instructions are the content of `terminal_hub_instructions`:

```
You have access to terminal_hub, a GitHub automation tool.

Rules:
1. During planning conversations, track each distinct task, bug, or feature mentioned by the user.
2. When you identify a clear, actionable task, call create_issue directly. The MCP approval prompt
   will ask the user to confirm — do NOT ask a separate natural language question first.
3. When calling create_issue, generate:
   - A concise, imperative title (e.g. "Fix authentication bug in login flow")
   - A detailed body covering: what the issue is, why it matters, and acceptance criteria
4. Update project_description.md and architecture_design.md any time the conversation introduces
   new information about the project goals, scope, or architecture — not only after issue creation.
   Always call get_project_context first to read existing content, then call the update tool
   with the full preserved-and-extended content. Never overwrite without reading first.
5. At the start of a new session, call list_issues to reload known issues,
   then call get_issue_context for any issue relevant to the current conversation.
6. Do not create duplicate issues. Check list_issues before creating a new one.
```

---

## User Workflow

1. **Install once**
   ```bash
   pip install terminal-hub
   ```

2. **Configure Claude Code MCP** — add to `~/.claude.json` (Claude Code CLI config):
   ```json
   {
     "mcpServers": {
       "terminal-hub": {
         "command": "terminal-hub",
         "env": {
           "GITHUB_TOKEN": "your_token_here"
         }
       }
     }
   }
   ```
   Optional override: `"GITHUB_REPO": "owner/repo"` if auto-detection from `git remote` is not desired.

3. **Start any project** — on Claude Code startup, the MCP server starts and auto-creates `.terminal_hub/` if needed.

4. **Load instructions** — run `/mcp terminal-hub terminal_hub_instructions` to inject the terminal_hub system prompt into the session. Alternatively, add the following to your project's `CLAUDE.md` to load it automatically: `Use terminal_hub_instructions from the terminal-hub MCP server at session start.`

5. **Plan in Claude Code** — user describes what they want to build in natural conversation.

6. **Claude creates issues** — mid-conversation, Claude identifies a distinct task and calls `create_issue` directly. Claude Code's MCP approval prompt appears: the user presses **y** to confirm or **n** to skip. There is no separate natural language question from Claude.

7. **On confirmation:**
   - GitHub issue is created with auto-generated title and description
   - `.terminal_hub/issues/fix-auth-bug.md` is written with full context
   - `project_description.md` and `architecture_design.md` are updated to reflect current state

8. **Living documents** — context files also update any time new project or architecture information emerges in conversation, not only after issue creation.

9. **Future sessions** — Claude calls `list_issues` then `get_issue_context` to reload just the relevant context, minimizing token usage.

---

## Local File Structure

```
<project-root>/
└── .terminal_hub/
    ├── project_description.md     # What the project does and its goals
    ├── architecture_design.md     # High-level architecture decisions
    └── issues/
        ├── fix-auth-bug.md        # Full context for this issue
        └── add-login-page.md
```

**Issue `.md` file format:**
```markdown
---
title: Fix auth bug
issue_number: 42
github_url: https://github.com/owner/repo/issues/42
created_at: "2026-03-15"
assignees: []
labels: []
---

<issue body content>
```

Users may commit `.terminal_hub/` to their repo (useful for teams) or add it to `.gitignore` (personal use only).

---

## Distribution

- **PyPI package:** `terminal-hub`
- **Entry point:** `terminal-hub` CLI command that starts the MCP server
- **Versioning:** Semantic versioning (`semver`)
- **Changelog:** `CHANGELOG.md` — format and minimum content are out of scope for this spec; maintained as a standard developer artifact per release
- **README:** One-page setup guide covering install, config, and first use — content is out of scope for this spec; minimum viable content is install command, MCP config snippet, and GitHub token setup

---

## Out of Scope (Future Work)

- Branch creation tied to issues
- `issues_agent/<issue_name>.md` agent workflow
- Slash command wrappers
- PR and code review automation
- Team/multi-user workflows
