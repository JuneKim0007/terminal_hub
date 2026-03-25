# terminal-hub

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-free%20to%20use-lightgrey.svg)](LICENSE)

> **Not yet on PyPI** — install by cloning the repo. See [Quick start](#quick-start).

---

## 1. Introduction

### **Conversation is the flow.**

terminal-hub is a Claude Code extension that turns your natural conversation into a full GitHub development workflow — planning, issue tracking, and implementation — without you having to manage the steps.

You describe what you want to build. terminal-hub handles the rest:

- 🗂 **GitHub management** — creates issues, assigns milestones, syncs labels, and closes issues automatically
- 🧠 **Context-rich implementation** — each issue carries step-by-step instructions so Claude always knows exactly what to do and why
- 🔄 **Bidirectional flow** — plan → implement → close, all from one conversation, with no manual orchestration

**The goal:** you focus on ideas. Claude handles the structure.

---

## 2. Why issues-based?

> *"It's not just about organizing your work — it's about removing the hardest part of vibe coding."*

The hardest part of AI-assisted development isn't writing code. It's writing **good prompts**. Vague prompts produce mediocre outputs. The real bottleneck is context — getting Claude to understand what you're building, why, and how it fits with what already exists.

terminal-hub solves this by turning your conversation into **structured, context-rich GitHub issues**. Each issue includes:

- What to build (from your description)
- How to build it (generated agent workflow with file paths, function names, conventions)
- Why it matters (linked to your project's design principles)

**The result:** Claude gets a self-contained brief for every task. You don't have to prompt it — the issue does the prompting for you.

And since it's all tracked as GitHub issues, you get version history, searchability, and team visibility for free.

---

## 3. Usage

### For any user — just start a conversation.

```
/th:gh-plan
```

Then just talk:

> *"I want to build a recipe app where users can save, tag, and search their own recipes"*

terminal-hub will:
1. Ask a few clarifying questions (stack, existing repo?)
2. Analyze your project (if one exists)
3. Break your idea into GitHub issues with full implementation context
4. Show you a preview — and only push to GitHub after you say **yes**

Then when you're ready to build:

```
/th:gh-implementation
```

> *"implement the recipe search issue"*

Claude loads the issue, reads the built-in workflow, and implements it. You review the diff and accept.

**That's it.** No manual context-writing. No step management. Just conversation.

---

## 4. Customization — built-in `.md` and `.json` behaviour files

terminal-hub's behaviour is driven by **plain text files** — `.md` skill files and `.json` config files — that ship with each command. These are not user files or global settings. They define exactly how Claude behaves during each workflow step.

### See what's loaded

```
/th:cmd-map
```

This shows every command, which skill files it loads, and which tools it calls. Use it to understand (and audit) exactly what terminal-hub does during any command.

### What you can change

| File type | What it controls | Where |
|-----------|-----------------|-------|
| `commands/*.md` | Claude's step-by-step behaviour for each command | `extensions/<plugin>/commands/` |
| `plugin_config.json` | Model routing, batch sizes, feature flags | `extensions/<plugin>/` |
| `hub_agents/config.yaml` | Your workspace preferences (persists across sessions) | Auto-created in your project |

### Changing a setting conversationally

```
/th:settings
```

> *"set coverage threshold to 90%"*
> *"turn off auto-close on GitHub"*

terminal-hub finds the right file, confirms the change, and writes it. You never need to edit JSON manually.

---

## 5. Dynamic customization — connecting your own files

Already have a project with your own `.md` design docs, `ARCHITECTURE.md`, or a `SKILLS.md`? terminal-hub can connect them.

### Option A — point Claude to your files

> *"connect my `docs/DESIGN.md` as the primary reference"*

terminal-hub links it via `docs_config.json`. From then on, it's automatically loaded as context during planning and implementation.

### Option B — see what's currently linked

```
/th:cmd-map
```

Shows all connected docs for every command. You can then:

- Tell Claude which to add/remove
- Edit `docs_config.json` manually
- Or just say *"disconnect the architecture doc from implementation"*

### The skills system

terminal-hub has a two-tier skill system:

- **Tier 1** — plugin-level skills that ship with terminal-hub (always available)
- **Tier 2** — your project skills (`hub_agents/skills/SKILLS.md`) that override or extend Tier 1

To add a project skill:

> *"create a starter skills file for this project"*

terminal-hub scaffolds `hub_agents/skills/SKILLS.md` and connects it automatically.

---

## 6. Integrating with an existing project

Two workflows depending on how much structure you have:

### Workflow 1 — Let it analyze everything

```
/th:gh-plan-analyze
```

terminal-hub walks your repo, reads key files, and builds a **design dictionary** (`project_summary.md` + `project_detail.md`). This becomes the context Claude references for every future issue and implementation — so it understands your codebase without you explaining it every time.

Best for: **projects with existing code** where you want terminal-hub to understand what's already built.

### Workflow 2 — Point it to your docs

If you already have architecture docs, API specs, or design notes:

> *"I have an `ARCHITECTURE.md` and a `docs/API.md` — use those as the reference for creating issues"*

terminal-hub connects them via `docs_config.json` and uses them as the source of truth instead of running a full analysis.

Best for: **projects with existing documentation** that you want to preserve and extend.

---

## Command reference

| Command | Say | Does |
|---------|-----|------|
| `/th:gh-plan` | "let's plan" | Full planning flow — analyze, create issues, push to GitHub |
| `/th:gh-plan-analyze` | "analyze my repo" | Build or refresh the design dictionary |
| `/th:gh-plan-list` | "list issues" | Show tracked issues with milestone grouping |
| `/th:gh-plan-create` | "create an issue" | Single guided issue with context lookup |
| `/th:gh-plan-setup` | "set up github" | Configure workspace and GitHub repo |
| `/th:gh-plan-auth` | "fix auth" | Recover from GitHub auth failures |
| `/th:gh-plan-unload` | "unload" | Clear all caches when done planning |
| `/th:gh-implementation` | "implement this issue" | Implement a tracked issue end-to-end |
| `/th:gh-docs` | "write docs" | Generate or update README + CONTRIBUTING |
| `/th:gh-auxiliaries` | "community standards" | Generate Code of Conduct, Security Policy, PR templates |
| `/th:settings` | "settings" | View and change all configurable values |
| `/th:cmd-map` | "show commands" | Map of all commands, skills, and tools |
| `/th:create-plugin` | "create a plugin" | Scaffold a new terminal-hub extension |
| `/th:current-stat` | "status" | Show what's currently loaded in session |

---

## 7. What's been built

terminal-hub was built using terminal-hub itself. Every issue was planned with `/th:gh-plan`, implemented with `/th:gh-implementation`, and tested automatically.

**Working today:**
- Full GitHub planning flow (`/th:gh-plan`) — repo analysis, issue creation with context-rich agent workflows, milestone management, label sync
- Implementation flow (`/th:gh-implementation`) — load issue, follow agent workflow, run filtered tests, review diff, commit and close
- Test generation (Step 6.5) — automatically creates or updates test files after implementation
- Test verification (Step 6.6) — runs pytest filtered to affected files, gates on coverage threshold
- Test failure handling (Step 6.6a) — classifies failures, loads suggestion files, offers fix/skip/adjust threshold
- Integrated startup calls — `pre_implementation()` and `post_implementation()` collapse 8-15 sequential MCP calls into single operations
- Settings manager (`/th:settings`) — conversational interface for all configurable values
- Community standards (`/th:gh-auxiliaries`) — Code of Conduct, Security Policy, PR/issue templates
- Docs generation (`/th:gh-docs`) — user and developer READMEs
- Plugin creator (`/th:create-plugin`) — scaffolds new extensions conversationally

---

## 8. Roadmap

### Coming next
- **`/th:settings` persistence** — flag changes written to `hub_agents/config.yaml` and loaded automatically each session
- **`finalize_implementation()` tool** — single call to commit, push, close GitHub issue, sync docs, and unload — the last 5 steps become one
- **Failure suggestion library** — more `suggestions/*.md` files covering common failure patterns per stack

### Considering
- **PyPI release** — `pip install terminal-hub` once the core API is stable
- **GitHub Discussions integration** — open discussion threads tied to planning sessions
- **GitHub Releases** — draft and publish releases from within the implementation flow
- **Docker support** — official `python:3.11-slim` setup guide for containerized environments

---

## Quick start

```bash
git clone https://github.com/JuneKim0007/terminal_hub
cd terminal_hub
pip install -e .
terminal-hub install    # registers MCP server + installs slash commands
# restart Claude Code
```

### Authentication

```bash
gh auth login          # recommended
# or
export GITHUB_TOKEN=ghp_...
```

### Requirements

- Python 3.10+
- Claude Code
- GitHub CLI (`gh`) — or set `GITHUB_TOKEN`
