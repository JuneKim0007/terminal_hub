---
name: milestones
description: Rules for deriving, creating, and assigning milestones to issues.
alwaysApply: false
triggers: [create_milestone, assign_milestone, milestone, sprint planning]
---

# Milestones — Rules

## Milestone Derivation (Step 2.5)

**Check `milestone_assign` preference first** via `read_preference("milestone_assign")`:
- If `True`: skip the question, go directly to deriving and creating milestones
- If `False`: skip milestones entirely this session
- If unset (None): proceed with derivation and present to user

**If unset**, derive 2–7 milestones from the saved project summary's feature groups.

Milestone construction rules (apply these, do not invent new ones):
- Each milestone covers a set of features that deliver user-visible value together
- Name milestones descriptively: "Core Auth", "Posting & Feed" — not "Milestone 1"
- Description = one sentence: what the user can do after this milestone ships
- A simple app needs 2–3 milestones; a large app 5–7

Show a compact table:
```
Proposed milestones:
  M1 — Core Auth: users can sign up, log in, and reset their password
  M2 — Posting: authenticated users can create, edit, and delete posts
  M3 — Launch Polish: performance, error handling, deploy pipeline

Create these on GitHub? (yes / no / yes, always create milestones)
```

- **"yes"** → call `create_milestone()` for each; cache results → persist to project_summary.md
- **"yes, always"** → call `create_milestone()` + `set_preference("milestone_assign", True)` → persist to project_summary.md
- **"no"** → proceed without milestones; no further milestone prompts this session; call `set_preference("milestone_assign", False)`

---

## Milestone Persistence Format

After creating milestones, call `update_project_summary_section(section_name="Milestones", content=...)`.

Use this format for the content:
```
| # | Name | Delivers |
|---|------|---------|
| M1 | Core Auth | Users can sign up, log in, and reset their password |
| M2 | Posting | Authenticated users can create, edit, and delete posts |
| M3 | Launch Polish | Performance, error handling, and deploy pipeline complete |
```

This is the authoritative milestone reference for agents implementing issues — they MUST check this section before asking "which milestone does this belong to?".

---

## Milestone Cache

Milestones are pre-fetched in Step 1 and live in `_MILESTONE_CACHE`. Do NOT call `list_milestones()` again after warming — use the cached data for issue assignment.

---

## Sequential Milestone Planning Preference

Check `sequential_milestone_planning` preference via `read_preference("sequential_milestone_planning")`.

- `True`: after submitting all issues for a milestone, automatically ask:
  > "M{n} issues submitted. Implement now or plan M{n+1}? (implement / plan next / done)"
  - "implement" → switch to /th:gh-implementation
  - "plan next" → call `generate_milestone_knowledge(n+1)` then continue Step 5 for next milestone
  - "done" → offer unload
- `False` or unset: no prompt (existing behavior)

---

## Planned Features Row Format

When adding new feature/enhancement issues to project_summary.md, use this row format:
```
| #{N} | {title} | M2 — Posting | feature, backend | api, backend |
```

Merge rows into the `## Planned Features` section — never replace the whole section.
