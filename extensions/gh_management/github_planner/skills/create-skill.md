---
name: create-skill
description: Rules for writing new skill files — frontmatter format, description quality, file size limits, structure conventions, and split rules. Load before creating any skill file to ensure it follows authoring best practices.
alwaysApply: false
triggers: [create skill, new skill, update_skill, skill authoring, write skill file]
---

# create-skill — Skill Authoring Rules

## When to Use

- Before creating any new skill file
- When calling `update_skill(name=...)` to create a skill
- When reviewing or improving an existing skill's frontmatter
- When deciding whether to split a skill into multiple files

## When NOT to Use

- When loading an existing skill to use its knowledge (use `load_skill` instead)
- When working on non-skill documentation

## Rules / Knowledge

### Frontmatter Rules

| Field | Rules |
|-------|-------|
| `name` | 64 chars max, kebab-case, lowercase. Domain-first naming: `auth-jwt.md`, `crud-pagination.md` — NOT `jwt-auth.md` |
| `description` | 1024 chars max, third-person POV. Must pass the description quality test (see below). |
| `alwaysApply` | `true` ONLY for pointer/index files like SKILLS.md and tools-overview.md. `false` for ALL knowledge content — no exceptions. |
| `triggers` | List of phrases that signal this skill is needed. Be specific. |

### Description Quality Test

"If an agent reads only this description, would it know exactly when to load this skill?"

- **Bad:** `"Auth skill"`
- **Good:** `"Rules for implementing JWT auth with FastAPI — covers token creation, refresh, and bcrypt password handling. Load when adding any authentication endpoint."`

### Size Target

- Target: < 200 lines / < 4000 tokens
- If > 200 lines: split into multiple files (see Split Rules)

### Required Structure (5 Sections)

1. Frontmatter (YAML between `---` markers)
2. `## When to Use`
3. `## When NOT to Use`
4. `## Rules / Knowledge`
5. `## Examples`

### Naming Convention

kebab-case, domain-first:
- `auth-jwt.md` ✓
- `crud-pagination.md` ✓
- `jwt-auth.md` ✗
- `paginationCrud.md` ✗

### Split Rules

**Split when:**
- Skill has 2+ unrelated trigger domains
- Exceeds 200 lines
- Is loaded in contexts where only half the content applies

**Never split** purely for length when all content shares one trigger domain.

## Examples

### Good frontmatter
```yaml
---
name: auth-jwt
description: Rules for implementing JWT auth with FastAPI — covers token creation, refresh, and bcrypt password handling. Load when adding any authentication endpoint.
alwaysApply: false
triggers: [JWT, authentication, token, bcrypt, login endpoint]
---
```

### Bad frontmatter (do not copy)
```yaml
---
name: Auth
description: Auth skill
alwaysApply: true
triggers: [auth]
---
```
Problems: name not kebab-case, description too vague, alwaysApply should be false for knowledge content.
