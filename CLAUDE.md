# CLAUDE.md — terminal-hub project rules

## Draft-first rule (non-negotiable)

Before writing any code, editing any file, or making any change to this project:

1. Call `draft_issue()` with a clear title, body, and `agent_workflow`
2. Show the draft to the user
3. Wait for explicit confirmation ("yes", "go", etc.)
4. Only then implement

**No exceptions** — not for small fixes, label changes, typos, or "obvious" patches.
This keeps every change traceable and gives the user veto power before anything lands.

If the user says "just do it" or "skip the issue" explicitly, proceed without drafting.

## Why

Issues are the context record for this project. A change without an issue is invisible
to future contributors and to the planning tools (`list_issues`, `load_active_issue`,
`project_summary.md`). Even a one-line fix deserves a slug.

## Other rules

- Always call `set_project_root(path=<cwd>)` as the first MCP tool call in any `/th:` command
- Never pass CoC/policy template text through Claude's context — use server-side atomic tools (`generate_and_write_coc`)
- Test coverage must stay ≥ 89% after any change
- Commit message format: `<type>: <description> (#<issue_number>)`
