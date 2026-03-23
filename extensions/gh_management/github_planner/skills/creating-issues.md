---
name: creating-issues
description: Rules for sizing issues, writing AC, generating agent_workflow steps, assigning labels, and building Planning Context blocks. Load when drafting or planning GitHub issues.
alwaysApply: false
triggers: [draft_issue, submit_issue, gh-plan, create issue, plan feature, size issue]
---

# Creating Issues — Rules

## Issue Sizing (Step 6a)

**If `dispatch_task` is available**, call `dispatch_task(task_type="issue_classification", prompt="{title}\n\n{body excerpt}")` and use the returned `size` directly.

**Otherwise** (fallback), apply the first matching rule:

| Size | Signal | agent_workflow | AC bullets |
|------|--------|----------------|------------|
| **trivial** | `chore`/`docs`/`refactor` only; single-file, no logic change | omit entirely | 1 line |
| **small** | Isolated bug fix or single-focus change | orientation step + 1–2 specific steps | 1–3 bullets |
| **medium** | New capability, 2–5 files touched | orientation + 3–5 steps | 3–5 bullets |
| **large** | Cross-cutting, new subsystem, multiple areas | orientation + 5+ steps | 5+ bullets |

If size is ambiguous, pick the smaller bucket — err on the side of less.

---

## Feature Section Lookup (Step 6b — medium/large only)

For **medium** and **large** issues with a milestone assigned:
1. Call `load_milestone_knowledge(milestone_number=N)` first.
   - If the knowledge file exists: use its `## Interface Contract` as the primary Planning Context. Skip `lookup_feature_section` — the knowledge file already has the relevant contract.
   - If no knowledge file (returns empty or error): fall back to `lookup_feature_section(feature="...")` for that area.

For **medium** and **large** issues with **no milestone**: call `lookup_feature_section(feature="...")`. Use returned section + global_rules in the issue body.

Skip for trivial/small — the overhead isn't worth it.

---

## Planning Context Block (Step 6c)

Append to each issue body — **omit entirely for trivial issues**.

**When knowledge file was loaded (preferred path):**
```markdown
## Planning Context
**Milestone:** M{n} — {title from knowledge file}
**Goal:** {Goal section from knowledge file}
**Interface contract:** {Interface Contract section from knowledge file}
**Sibling issues:** #{slug} — {title} [{labels}] (from _ISSUE_LANDSCAPE filtered by same milestone_number)
**Layers affected:** {layers listed in Interface Contract}
```

**When no knowledge file (fallback path):**

First issue in a milestone batch (or no active milestone) — full block:
```markdown
## Planning Context
**Milestone:** {Mx — Name} — *{what this milestone delivers}*

**Sibling issues:** #{slug} — {title} [{labels}] · *(none yet)*

**Interface layers:** {layers from `## Interface Layers` in project_summary.md}
```

Subsequent issues in the same milestone batch — slim reference:
```markdown
## Planning Context
Milestone context same as #{first_slug_in_batch}. This issue: {one-sentence scope delta}.
**Interface layers:** {layers if different, otherwise omit}
```

Rules:
- Omit milestone lines if no milestone is assigned
- Omit interface layers line if `## Interface Layers` absent from project_summary.md and no knowledge file loaded
- Siblings come from `_ISSUE_LANDSCAPE` filtered by same `milestone_number`

---

## AC Format Rules (Step 6d)

**AC bullets: verb-object, ≤10 words each. No prose.**
- ✓ `"Submit creates a GitHub issue with correct labels"`
- ✗ `"When the user clicks the submit button, a new issue should appear..."`

---

## agent_workflow Generation (Step 6e)

Generate based on size:

- **trivial** → omit `agent_workflow` field entirely
- **small** → orientation step only + 1–2 specific steps:
  - Step 1: `"Skim the relevant file(s) for this change, check for existing patterns, make the fix."`
  - Steps 2–3: specific to this issue
- **medium/large** → orientation step + issue-specific steps:
  - Step 1: `"Orient yourself as an experienced developer picking up this task. If dispatch_task is available: call dispatch_task('structure_scan', file_tree_content) to get an area map, and call dispatch_task('file_location', issue_title + body) to get relevant files — use results to inform your concrete plan. Otherwise: if project docs exist (project_summary.md, project_detail.md), scan their headings — read only sections relevant to this area; if no docs, list files and filter by relevance. Stop once you have enough context. State your concrete plan: what you'll change, where, in what order, and what to watch for."`
  - Steps 2–N: specific to this issue (derived from body, AC, feature section)
  - Final step: `"Verify full test suite passes and all AC are met"`

**Do NOT prescribe which files to read. Do NOT use generic steps. Every step after Step 1 must be specific to this issue.**

---

## Label Auto-assignment (Step 6f)

Label cache is already warm from Step 1 — use cached label names (do NOT call `list_repo_labels()` again).

Check `label_auto_assign` preference (default `true`):
- If `true`/unset: infer from issue title + body using these rules (apply all that match; only use names in `_LABEL_CACHE` or `labels.json`):

| Condition | Label |
|-----------|-------|
| Title/body contains "fix", "bug", "broken", "error", "crash", "regression" | `bug` |
| Contains "feat", "add", "implement", "create", "new" | `feature` or `enhancement` |
| Contains "refactor", "cleanup", "rename", "move", "reorganise" | `refactor` |
| Contains "test", "spec", "coverage" | `test` |
| Contains "doc", "readme", "changelog", "comment" | `documentation` |
| Contains "slow", "cache", "optimise", "perf", "performance" | `performance` |
| Backend files mentioned (*.py, routes, models, services) | `backend` |
| Frontend files mentioned (*.tsx, *.jsx, components) | `frontend` |
| Auth-related (login, token, OAuth, JWT) | `auth` |

Always assign at minimum: one **type label** (bug/feature/enhancement/refactor/chore/documentation/performance). Add **area label** (`backend`, `frontend`, `auth`, `api`, `ci`, etc.) if identifiable from title/body/files.

Show auto-assigned labels in the confirmation block: `[feat] Add OAuth refresh → M1 Core Auth [auto]`

- If `false`: leave empty.

---

## Milestone Auto-assignment (Step 6f)

Check `milestone_auto_assign` preference (default `true`):
- If `true`/unset (stop at first match):
  1. Title/body references a version or sprint string → assign matching milestone from `_MILESTONE_CACHE`
  2. Exactly one active milestone in `_MILESTONE_CACHE` → assign silently
  3. Multiple active milestones → use `dispatch_task("issue_classification", issue_title + body)` if available to determine likely milestone from size + area; show result and let user override
  4. Multiple milestones, no dispatch_task → ask: "Which milestone? ({names}) / skip"
  5. No milestones → leave unassigned

- Never auto-create a milestone for a single issue.
- **Do NOT auto-assign milestone when:** issue is a question/discussion/support request, labelled `wontfix`/`duplicate`/`invalid`, or is a tracking/epic issue spanning multiple deliverables.

---

## Overlap Check (Step 5)

Scan `_ISSUE_LANDSCAPE` for existing issues with similar title or feature area. If found, surface it before planning:

> "This looks similar to #{slug} — {title}. Extend that issue, or create a new one?"

Do not silently duplicate.
