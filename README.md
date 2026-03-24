# terminal-hub

[![PyPI version](https://img.shields.io/pypi/v/terminal-hub.svg)](https://pypi.org/project/terminal-hub/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-free%20to%20use-lightgrey.svg)](LICENSE)

**NOT YET DEPLOYED — not on PyPI or the Claude plugin marketplace.** Installation is manual — clone the repo and follow [Quick start](#quick-start) below. PyPI and marketplace support are on the roadmap for v1.0.

_**”Conversation is the flow”**_ is the core philosophy of this backend Claude layer.

The project aims to simplify developer workflows by enabling conversation-driven automation, where tasks like planning, implementation, and tooling are handled through natural interaction instead of manual orchestration.

Terminal-hub so far provides a system where specialized components—such as a GitHub planner and an implementor—communicate bidirectionally to execute tasks efficiently. This conversational loop allows the system to dynamically plan, act, and refine outcomes with minimal user friction.

The framework is designed to be highly OS-compatible and error-tolerant, relying primarily on Claude APIs and GitHub CLI commands and built-in Python framework to ensure portability across different environments and architectures. BUT full compatibility across all systems cannot be guaranteed.

If you wish to run on a docker environment, it is recommended to run the framework using a minimal Python Docker image such as python:3.11-slim.

Ships with **github_planner** (issue management + repo analysis) and **plugin_creator** (conversational plugin scaffolding) as built-in extensions.

---

## The idea

Most GitHub automation tools require you to manually invoke each step. terminal-hub flips this: you describe what you're planning, and the system handles the rest — workspace setup, repo analysis, context loading, issue creation, and cleanup — all in one flow.

The deeper goal is to give Claude a **rich, structured context** so it can perform at a higher level. Rather than relying on Claude to infer project intent from raw code, terminal-hub maintains a living design dictionary (`project_summary.md`, `project_detail.md`), per-issue agent workflows, and a two-tier skill system — all loaded selectively so Claude always has exactly the right context for the task at hand.

This is grounded in how Claude actually works best: detailed, step-by-step instructions with relevant context produce significantly better outcomes than vague prompts. terminal-hub is a framework for making that kind of context-richness systematic and automatic, rather than something each developer has to hand-craft for every session.

---

## Design tradeoffs

Some features were deliberately left out because the token cost outweighs the gain:

- **Eager context loading** — loading all project docs at session start. Instead, terminal-hub loads only `project_summary.md` (≤500 tokens) upfront and fetches detail sections on demand via `lookup_feature_section`.
- **Auto-analysis on every save** — watching for file changes and re-running repo analysis automatically. The overhead of continuous scanning is not worth it for most workflows; analysis runs on demand or when docs are >7 days stale.
- **Full plugin registry dumps** — returning all plugin metadata to Claude on every command load. Only the relevant slice is returned; the rest stays on disk.

The rule of thumb: every token Claude loads must earn its keep. If a piece of context isn't needed for the current task, it shouldn't be in the prompt.

---

## A note for new users — reading issues

> **Before diving in, read the open issues on GitHub.**
> terminal-hub uses itself to track its own development, so the issue list reflects real design decisions, known gaps, and planned improvements. At minimum, skim the open issues. The recommendation is to build a general understanding of the code flow before contributing — the architecture is intentional and issues explain the *why* behind it.

---

## Prompting tip

If you're not a confident prompter, the most reliable thing you can do is explicitly tell the AI its core principle at the start of every session:

> *"Remember: your core principle for this project is [X]. Always [Y] before [Z]."*

With terminal-hub this is handled automatically — `project_summary.md` and the skills system inject your design principles into every relevant session so Claude never forgets them. Without a framework like this, you need to be intentional and explicit every time.

---

## Built with terminal-hub

terminal-hub was developed using terminal-hub itself, alongside the [everything-claude-code](https://github.com/disler/everything-claude-code) plugin suite. Issues were planned with `/th:gh-plan`, implemented with `/th:gh-implementation`, reviewed with ECC's code-review and TDD skills, and docs generated with `/th:gh-docs`. The workflow described in this README is the one used to build it.

---

## What's been built — how it works internally

Every action in terminal-hub is a sequence of named MCP tool calls. This section walks through each flow in plain language so you know exactly what happens under the hood.

---

### Planning an issue (`/th:gh-plan`)

When you say "let's plan", here is what fires in order:

1. **`set_project_root(path)`** — anchors the `hub_agents/` directory to your project, not the terminal-hub install location. Every subsequent file write goes to the right place.
2. **`apply_unload_policy("gh-plan")`** — reads the unload policy, identifies caches from any previous session (analysis snapshots, file trees, label caches), and clears them in Python. Claude only sees the one-line result.
3. **`confirm_session_repo()`** — checks whether the active GitHub repo matches what's in `hub_agents/config.yaml`. If it doesn't match, you're asked to confirm or change it before anything else happens.
4. **`load_project_docs(doc="summary")`** — reads `hub_agents/extensions/gh_planner/project_summary.md` (capped at ≤500 tokens). This contains your tech stack, design principles, and known pitfalls — the context Claude needs to plan correctly.
5. **`get_session_header()`** — builds a compact status banner: current repo, mode (local/github), open issue count, and whether analysis is stale. Printed once at the top of the planning session.
6. **Planning conversation begins.** You describe what you want to build. Claude uses the loaded design principles to shape each issue.
7. **`draft_issue(title, body, labels, agent_workflow)`** — saves the issue locally to `hub_agents/issues/<slug>.md` with YAML frontmatter. Status is `pending`. Nothing goes to GitHub yet. You see a preview.
8. **`submit_issue(slug)`** — on your approval, reads the local draft, bootstraps any missing GitHub labels via the API if needed, then creates the issue on GitHub. Updates the local file status to `open`.
9. **`generate_issue_workflows(slug)`** — appends two structured sections to the issue: an **Agent Workflow** (step-by-step implementation instructions for Claude) and a **Program Workflow** (change type, affected components, test checklist). This is what makes each issue self-contained.
10. **`update_project_detail_section(feature, content)`** — if the new issue touches a feature area not yet in your design dictionary, Claude merges a new section into `project_detail.md` without rewriting existing sections.
11. **`unload_plugin()`** — when you're done, all in-memory caches are cleared. Your issues and docs on disk are preserved.

---

### Analyzing a repo (`/th:gh-plan-analyze`)

1. **`get_file_tree()`** — walks the repo and builds a nested file tree, cached to `file_tree.json` with a 1-hour TTL. Skips `hub_agents/`, `.git/`, and common noise directories.
2. **`create_scan_profile()`** — classifies the repo: detects language, framework, entry points, and test layout. Stored as a scan profile used to guide which files are worth reading.
3. **`start_repo_analysis()`** — kicks off a batched read of the most relevant source files, prioritising entry points, config files, and core modules. Files are grouped into batches to stay within token limits.
4. **`fetch_analysis_batch(batch_id)`** — called repeatedly until all batches are processed. Each call reads a set of files and accumulates findings: patterns, conventions, design decisions.
5. **`save_project_docs(summary, detail)`** — writes two files:
   - `project_summary.md` — high-level: tech stack, architecture style, design principles (≤500 tokens)
   - `project_detail.md` — deep: one section per feature area with existing design notes and extension guidelines
6. **`update_architecture()`** — if an `architecture_design.md` already exists, its relevant sections are merged rather than overwritten.

---

### Implementing an issue (`/th:gh-implementation`)

1. **`set_project_root(path)`** — same anchor step as planning.
2. **`apply_unload_policy("gh-implementation")`** — clears planning caches (analysis results, session headers) that aren't needed during implementation.
3. **`load_project_docs(doc="summary")`** — loads design principles so Claude knows the conventions before touching code.
4. **`list_issues()`** — reads all `hub_agents/issues/*.md` files and returns a compact table of open issues. You pick one.
5. **`load_active_issue(slug)`** — reads the chosen issue file in full. Returns the issue body, labels, frontmatter, and — critically — the `agent_workflow` field that was generated at planning time. This workflow is the authoritative implementation guide; Claude follows it step by step.
6. **`lookup_feature_section(feature)`** — if the issue references a feature area, the relevant section from `project_detail.md` is fetched and loaded. Only the matching section, not the whole file.
7. **Implementation happens.** Claude works through the agent workflow steps, editing files and running tests. No prompting needed unless blocked.
8. **`git diff HEAD`** — once implementation is done, the full diff is shown. You review it.
9. **Commit, push, close.** On your approval: `git commit`, `git push`, then `close_github_issue(issue_number)` via the GitHub API. The local issue file is deleted by `unload_active_issue()`.

---

### Writing docs (`/th:gh-docs`)

1. **`hub_agents/docs_guide.md` check** — reads your saved preferences (tone, structure, what to include/exclude). If the file doesn't exist, a default scaffold is created.
2. **`load_skill("create_user_readme_docs")`** or **`load_skill("create_dev_readme_docs")`** — loads the relevant skill file into context. The skill contains exact structure rules, writing conventions, badge templates, and before/after examples.
3. **Existing files are read first** — if `README.md` or `CONTRIBUTING.md` already exist, they're read before any generation. Only sections that need updating are patched; structure you've customised is preserved.
4. **Content is generated in context** — nothing is written to disk until you confirm. A headings-only preview is shown first.
5. **`git add README.md CONTRIBUTING.md`** → commit → push or PR. Only these two files are staged — never `git add .`.

---

### Creating a plugin (`/th:create-plugin`)

1. Conversational scaffolding — Claude asks for plugin name, description, and what tools it needs.
2. **`validate_plugin(manifest)`** — checks the proposed `plugin.json` against the required field schema before writing anything.
3. **`write_plugin_file(path, content)`** — writes each file one at a time: `plugin.json`, `__init__.py` with `register(mcp)` stub, `description.json`, and at least one command `.md` file.
4. **`write_test_file(path, content)`** — generates a test scaffold in `tests/tools/test_<name>.py` with the standard `_do_*` pattern and filesystem mocking fixtures.
5. `terminal-hub install` is suggested at the end to copy the new command files to `~/.claude/commands/th/`.

---

## Roadmap

### Confirmed

- **GitHub community standards** — auto-generate and configure issue templates, pull request templates, security policy (`SECURITY.md`), and code of conduct (`CODE_OF_CONDUCT.md`) on demand via a single command
- **Stabilize `/th:create-plugin`** — the plugin scaffolding flow works but needs hardening: better validation, test coverage, and error recovery
- **Auto-assign issue templates** — when creating an issue, detect the appropriate GitHub issue template and apply it automatically rather than always using a blank form
- **`.gitignore` management** — generate or update `.gitignore` based on detected stack during repo analysis; suggest additions when new file types are introduced
- **GitHub Releases** — at v1.0, add support for drafting and publishing GitHub releases from within the planning or implementation flow

### Considering

- **GitHub Discussions** — open and manage discussion threads tied to planning sessions; useful for async teams
- **Automated model deployment** — a possible future extension for projects that deploy AI models: trigger deploy pipelines, track model versions, and surface deployment status in the planning flow

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
/th:gh-plan
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

## Slash commands reference

| Command | Say | Does |
|---------|-----|------|
| `/th:gh-plan` | "let's plan" | Full planning flow — setup, analyze, create issues |
| `/th:gh-plan-create` | "create an issue" | Single guided issue with project context lookup |
| `/th:gh-plan-analyze` | "analyze my repo" | Build or refresh the design dictionary |
| `/th:gh-plan-list` | "list issues" | Show tracked issues as a table |
| `/th:gh-plan-setup` | "set up github" | Configure workspace and GitHub repo |
| `/th:gh-plan-auth` | "fix auth" | Recover from GitHub auth failures |
| `/th:gh-plan-settings` | "planner settings" | View or toggle planning preferences |
| `/th:gh-plan-unload` | "unload" | Clear all caches manually |
| `/th:gh-implementation` | "implement this issue" | Implement a tracked issue end-to-end |
| `/th:gh-docs` | "write docs" | Create or update README.md + CONTRIBUTING.md, then PR or push |
| `/th:current-stat` | "status" | Show what's currently loaded |

For most workflows, **just use `/th:gh-plan`** — it composes all of these.

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

## Documentation

Full user documentation is in [docs/user/](docs/user/):

- [Installation](docs/user/installation.md) — install and configure terminal-hub
- [Quick Start](docs/user/quick-start.md) — plan and implement your first issue in 5 minutes
- [Slash Commands](docs/user/commands.md) — full reference for all `/th:` commands
- [Configuration](docs/user/configuration.md) — environment variables and workspace layout

---

## Requirements

- Python 3.10+
- Claude Code
- GitHub CLI (`gh`) for GitHub features — or set `GITHUB_TOKEN`
