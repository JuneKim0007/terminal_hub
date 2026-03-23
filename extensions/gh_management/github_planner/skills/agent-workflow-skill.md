---
name: agent-workflow
description: Rules for writing agent_workflow steps that are safe for a zero-context implementing Claude. Load before writing any agent_workflow field. Forces explicit file paths, function names, and context embeddings.
alwaysApply: false
triggers: [draft_issue, writing agent_workflow, context enrichment]
---

# agent-workflow Skill

Rules for writing `agent_workflow` steps. Every step must be written for a Claude with **zero context** — no conversation, no open files, no memory.

## Rules

1. **NEVER say "the auth file"** — always say the explicit path: `src/auth/service.py`
2. **NEVER say "the existing function"** — always say `TokenService.create()` at `src/auth/service.py`
3. **For every file the planning Claude consulted**: embed the path and why it matters
4. **For every reusable function discovered**: name it, path it, describe its interface
5. **For every convention that applies**: state it explicitly — e.g. `"JWT secret via settings.SECRET_KEY, never hardcode"`
6. **For every pitfall discovered during planning**: warn explicitly — e.g. `"watch for session flush in TokenCache.clear() — clears all users"`
7. **For every project_detail section relevant**: include load instruction — e.g. `"call lookup_feature_section('Auth') for the full endpoint spec"`
8. **For every design principle that governs this change**: embed it — e.g. `"layered: route → service → repo — no direct DB calls from routes"`
9. **The implementing Claude must be able to read `agent_workflow` alone** and know exactly where to start, what to open, and what to avoid.

## Step Format

```
"[verb] [what] — [where exactly] — [what to know]"
```

**Good examples:**
- `"Extend TokenService.create() in src/auth/service.py — add refresh_token return field — keep existing validation logic intact"`
- `"Add /api/v1/auth/refresh route in src/auth/routes.py — follows same FastAPI pattern as /login — must validate via verify_token()"`
- `"Run pytest tests/auth/ after each change — test_token_expiry.py covers the 24h window we're implementing"`

**Bad examples (never do this):**
- `"Update the auth service"` — no path, no function name
- `"Use the existing helper"` — which helper? where?
- `"Follow the existing pattern"` — which pattern? state it explicitly

## Checklist Before Submitting

- [ ] Every step names specific files, not "the file" or "the service"
- [ ] Every referenced function includes its module path
- [ ] At least one step covers the test to run after implementing
- [ ] Any discovered pitfalls are called out with explicit warnings
- [ ] Design principles that apply are embedded in the relevant step, not assumed
