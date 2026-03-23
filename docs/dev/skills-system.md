# Skills System

How the two-tier skill system works — Tier 1 plugin-level skills and Tier 2 project-level skills.

---

## What skills are

Skills are reusable prompt fragments stored as `.md` files with YAML frontmatter. Unlike commands (which are entry points invoked by slash commands), skills are loaded on demand from within a command when their content is needed.

A skill might contain: implementation rules, diff presentation format, doc update decision tables, writing conventions, or any other reusable instructions that multiple commands need.

---

## Two tiers

| | Tier 1 — Plugin skills | Tier 2 — Project skills |
|--|----------------------|------------------------|
| Location | `extensions/<plugin>/skills/*.md` | `hub_agents/skills/*.md` |
| Shipped with | The plugin (version-controlled) | The project (gitignored, per-project) |
| Scope | Available in any project using this plugin | Available only in this project |
| Who creates | Plugin author | Project owner / user |
| Example | `implementing.md` — workflow rules for gh-implementation | `SKILLS.md` — project-specific coding conventions |

Both tiers are resolved by `load_skill()`. Tier 1 is checked first; Tier 2 overrides if a matching name exists.

---

## Skill file format

```markdown
---
name: my-skill
description: What this skill does — used to decide relevance in future sessions.
alwaysApply: false
triggers:
  - phrase that triggers this skill
  - another trigger phrase
---

# my-skill

Skill content here. This is what gets loaded into Claude's context.

## Section A

Rules, tables, examples, anything Claude should follow.
```

**Frontmatter fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier used in `load_skill("name")` calls |
| `description` | Yes | One-line summary — used by `/th:skill-map` and to decide relevance |
| `alwaysApply` | No (default: false) | If `true`, skill is auto-loaded when `set_project_root` is called |
| `triggers` | No | Phrases that signal this skill is relevant |

---

## Loading a skill

From within a command `.md` file:

```markdown
<!-- SKILL: load_skill("implementing") — contains workflow derivation rules -->
```

Or inline in a step:

```markdown
## Step 5 — Define workflow

Call `load_skill("implementing")` and follow the workflow derivation rules it returns.
```

The `load_skill(name)` MCP tool:
1. Checks Tier 2 path (`hub_agents/skills/<name>.md`) first
2. Falls back to Tier 1 (`extensions/<plugin>/skills/<name>.md`)
3. Returns the full skill content + metadata

---

## alwaysApply skills

Skills with `alwaysApply: true` are automatically loaded when `set_project_root()` is called at the start of any command. Use this for skills that should always be active — e.g. project-wide coding conventions, design principles.

```markdown
---
name: project-conventions
description: Coding conventions for this project — always active.
alwaysApply: true
---
```

---

## Introspection

```
/th:skill-map
```

Lists all skills (both tiers) with their `alwaysApply` status, triggers, and which commands reference them. Auto-rebuilds if any skill file has changed since the last scan.

---

## When to write a skill vs a command

| Write a skill when... | Write a command when... |
|----------------------|------------------------|
| The content is reused by multiple commands | It's a user-facing entry point |
| It's a set of rules, not a flow | It orchestrates a multi-step flow |
| It's too small to be its own slash command | The user invokes it directly |
| Example: diff presentation format | Example: `/th:gh-implementation` |
