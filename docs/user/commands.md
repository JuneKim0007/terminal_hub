# Slash Commands Reference

Full reference for all `/th:` commands available in Claude Code via terminal-hub.

---

## Planning

### `/th:gh-plan`
**Say:** "let's plan", "plan some work", "I want to plan a feature"

The integrated planning flow. Handles everything: workspace setup, repo analysis, context loading, issue drafting, confirmation, submission, and cleanup. **This is the only command most users need.**

Sub-commands (called automatically within the flow, or directly):

| Sub-command | Say | Does |
|-------------|-----|------|
| `/th:gh-plan-setup` | "set up github", "configure the repo" | First-time workspace init — sets GitHub repo, mode, and auth |
| `/th:gh-plan-analyze` | "analyze my repo", "read the codebase" | Scans codebase to generate `project_summary.md` and `project_detail.md` |
| `/th:gh-plan-create` | "create an issue", "draft an issue", "log a bug" | Draft and submit a single issue with full project context |
| `/th:gh-plan-list` | "list issues", "what's open" | Show all tracked issues as a table |
| `/th:gh-plan-auth` | "fix auth", "github login" | Recover from GitHub authentication failures |
| `/th:gh-plan-settings` | "planner settings", "planning preferences" | View or toggle automation preferences |
| `/th:gh-plan-unload` | "unload", "clear cache", "free memory" | Clear all cached data from Claude's context |

---

## Implementation

### `/th:gh-implementation`
**Say:** "implement this issue", "work on an issue", "let's implement"

End-to-end issue implementation flow. Loads issue context and agent workflow, implements the changes, shows a diff for review, then commits, pushes, and closes the issue.

| Sub-command | Does |
|-------------|------|
| `/th:gh-implementation/implement` | Run the full implementation flow for a specific issue |

---

## Community Standards

### `/th:gh-auxiliaries`
**Say:** "community standards", "code of conduct", "security policy"

Generates GitHub community standard files on demand. Never auto-triggered — always requires explicit invocation.

| Sub-command | Does |
|-------------|------|
| `/th:gh-auxiliaries/code-of-conduct` | Generate `CODE_OF_CONDUCT.md` with template selection and metadata injection |

---

## Documentation

### `/th:gh-docs`
**Say:** "write docs", "update docs", "generate documentation"

Creates or updates `README.md` and/or `CONTRIBUTING.md`. Asks whether to open a GitHub PR for review or push directly to main. Automatically prompted after all issues are closed.

---

## Introspection

### `/th:current-stat`
**Say:** "status", "what's loaded", "show state"

Shows what's currently loaded in the workspace: active issue, project docs, session flags, and cache state.

### `/th:skill-map`
**Say:** "skill map", "show skills", "which skills exist"

Lists all plugin skills with their triggers and which commands use them. Auto-rebuilds if any skill file has changed.

### `/th:cmd-map`
**Say:** "command map", "show commands", "list commands"

Lists all commands with the skills they load and the MCP tools they reference.

---

## Plugin creation

### `/th:create-plugin`
**Say:** "create a plugin", "new plugin", "scaffold a plugin"

Conversational plugin scaffolding. Generates `plugin.json`, `__init__.py`, `description.json`, command files, and a test scaffold — one step at a time.

---

## Tips

- For most workflows, **just use `/th:gh-plan`** — it composes all planning sub-commands.
- All commands are bidirectional: `/th:gh-implementation` detects planning intent and offers to switch to `/th:gh-plan`, and vice versa.
- Use `/th:gh-plan-unload` when finished to free Claude's context before starting a new task.
