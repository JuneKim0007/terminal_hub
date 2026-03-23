---
name: workflow
description: Rules for writing the Workflow body section — human-readable planning narrative that captures intent, context found, design decisions, and completion criteria. Load before writing the ## Workflow section.
alwaysApply: false
triggers: [draft_issue, writing workflow, context enrichment]
---

# workflow Skill

Rules for writing the `## Workflow` body section of an issue. This is the human-readable planning narrative — not the machine-executable steps (`agent_workflow`).

## Rules

1. **Start with what the user actually asked for, expanded** — not `"add auth"` but `"implement JWT auth with 24h expiry, refresh tokens, and bcrypt password hashing"`.

2. **State which interface layers are touched** — from `project_summary.md` Interface Layers or design principles. Example: `"Touches: routes layer (new endpoints) + service layer (TokenService) + repository layer (RefreshTokenRepo)"`.

3. **State which design principles govern this change** — from `project_summary.md` Design Principles. Example: `"Applies: layered architecture (no direct DB in routes), test coverage ≥ 80%, JWT secret via settings.SECRET_KEY"`.

4. **List what was found in the internal scan** using these three categories:
   - `"Reusing: TokenService (src/auth/service.py) — already handles token generation"`
   - `"Extending: UserModel (src/models/user.py) — adding password_hash field"`
   - `"Building new: RefreshTokenRepo (src/repositories/refresh.py) — nothing exists"`

5. **State the "why" for non-obvious decisions** — e.g. `"using bcrypt over argon2 because existing password check uses bcrypt — do not mix hashing strategies"`.

6. **Reference the milestone if set** — e.g. `"targets M1 — Core Auth: users can sign up and log in securely"`.

7. **Include the acceptance criteria anchor** — `"done when [specific observable outcome]"` — e.g. `"done when POST /api/v1/auth/login returns access_token + refresh_token and test_auth_flow.py passes"`.

## Template

```markdown
## Workflow

**Intent:** [expanded user request]

**Layers touched:** [route / service / repository / model / ...]

**Design principles applied:**
- [principle 1 from project_summary.md]
- [principle 2]

**Internal scan:**
- Reusing: [name] ([path]) — [why relevant]
- Extending: [name] ([path]) — [what changes]
- Building new: [name] ([path]) — [what it does]

**Key decisions:**
- [decision] — [why not alternative]

**Milestone:** [M#] — [milestone title] (or N/A)

**Done when:** [specific observable outcome]
```

## Anti-Patterns

- **Vague intent**: `"Add auth support"` → expand to full feature description
- **Missing scan results**: Omitting what was found forces the implementing Claude to re-discover everything
- **No "done when"**: Without a concrete acceptance anchor, implementation has no endpoint
- **Missing design constraints**: The implementing Claude will violate conventions it doesn't know about
