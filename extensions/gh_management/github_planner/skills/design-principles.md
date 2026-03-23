---
name: design-principles
description: Rules for when and how to update project_summary.md and project_detail.md after planning or shipping a feature.
alwaysApply: false
triggers: [update_project_detail_section, update_project_summary_section, feature shipped, architecture change]
---

# Design Principles — Doc Update Rules

## When to Update Docs

### After Planning (gh-plan Step 6h)

Skip all doc updates for **trivial** and **small** issues.

For **medium/large**, check `confirm_arch_changes` preference first:
- `true` or unset → show one-line preview, ask "Update project notes? (yes/no)"
- `false` → update silently

### After Shipping (gh-implementation Step 9)

After pushing and closing, update project docs to reflect what was actually built.
Read the closed issue's labels from its local file frontmatter, then apply the decision table below.

Before writing, check `confirm_arch_changes` preference:
- `true` or unset → show a one-line preview and ask "Update project notes? (yes/no)" before calling any update tool
- `false` → update silently

---

## Doc Update Decision Table (Labels → Actions)

| Labels | Action |
|--------|--------|
| `enhancement` or `feature` | (a) `update_project_detail_section(feature_name, content)` — include `**Milestone:** Mx` at top. (b) `update_project_summary_section(section_name="Planned Features", content=...)` — merge rows, never replace. |
| `architecture` | `update_project_summary_section(section_name="Design Principles", content=...)` |
| `bug`, `chore`, `refactor`, `docs` only | **No update** — skip entirely |
| No labels | Ask: "Should I add this to the design notes? (yes/no)" — then follow the appropriate row above |

---

## Tool Usage Rules

**`update_project_detail_section`** — use when:
- Issue labels include `enhancement` or `feature`
- Need to add or update a specific feature area in project_detail.md
- Architecture label — use for Design Principles section
- Never call for bug/chore/refactor/docs-only issues

**`update_project_summary_section`** — use when:
- After milestone creation: `section_name='Milestones'`, `table_rows=[{"#":"M1","Name":"...","Delivers":"..."}]`
- Architecture change: `section_name='Design Principles'`, `items=[...]`
- Adding to Planned Features: `section_name='Planned Features'`, merge rows

**Both tools** are surgical — they replace/append only the named H2 section, never the full file. This prevents accidental truncation.

---

## `confirm_arch_changes` Preference Behavior

| Preference value | Behavior |
|-----------------|----------|
| `true` | Always show one-line preview + ask "Update project notes? (yes/no)" |
| `false` | Update silently, no prompt |
| unset (None) | Treat as `true` — ask before updating |

Set via: `set_preference("confirm_arch_changes", True/False)`
Ask once during new-repo setup:
> "When I update your project design notes in the future, should I always ask you first, or just do it silently? (always ask / just do it)"
