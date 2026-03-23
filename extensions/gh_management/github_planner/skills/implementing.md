---
name: implementing
description: Rules for deriving agent_workflow steps and presenting diffs during issue implementation.
alwaysApply: false
triggers: [load_active_issue, gh-implementation, implement issue, work on issue]
---

# Implementing — Rules

## Workflow Derivation (Step 5)

When an issue has no `agent_workflow`, derive one from: issue title, body, labels, matching feature section from project_detail.md, and design principles from project_summary.md.

**First infer the issue's size** from its labels and scope:

**If `dispatch_task` is available**: call `dispatch_task(task_type="issue_classification", prompt="{title}\n\n{body excerpt}")` and use the returned `size` directly.

**Otherwise** (fallback — same rules as gh-plan Step 6a):

| Size | Signal |
|------|--------|
| **trivial** | `chore`/`docs`/`refactor` only; single-file, no logic change |
| **small** | Isolated bug fix or single-focus change |
| **medium** | New capability, 2–5 files touched |
| **large** | Cross-cutting, new subsystem, multiple areas |

### Workflow steps by size:

- **trivial** → no workflow needed; just make the change

- **small** → `"Skim the relevant file(s), check for existing patterns, make the fix."` + 1–2 specific steps

- **medium/large** → orientation step:
  `"Orient yourself as an experienced developer picking up this task. If dispatch_task is available: call dispatch_task('structure_scan', file_tree_content) to get an area map, and call dispatch_task('file_location', issue_title + body) to get relevant files — use results to inform your concrete plan. Otherwise: if project docs exist (project_summary.md, project_detail.md), scan their headings — read only sections relevant to this area; if no docs, list files and filter by relevance. Stop once you have enough context. State your concrete plan: what you'll change, where, in what order, and what to watch for."`
  Then add issue-specific steps for 2–N.

**Do NOT prescribe which files to read** — let the agent decide based on the issue.

Call `draft_issue` or update the issue file to persist the workflow before proceeding.

---

## Diff Presentation Format (Step 7)

Run `git diff HEAD` (Bash tool), then present in two blocks — **never dump raw patch**.

**Block 1 — Workflow summary** (what the agent did, one line per step completed):
```
What was done:
1. Strategy: read project_summary + project_detail/{area} — identified N files in scope across {layers}
2. <specific action taken for this issue>
3. Added/updated tests: <what was tested>
4. Verified: N tests pass, coverage N%
```

**Block 2 — Diff summary** (structured, not raw patch):
```
Files changed:
  M  src/auth.py        +24 / -3
  A  tests/test_auth.py +41

Key changes:
- src/auth.py: <plain English description of change>
- tests/test_auth.py: <plain English description>
```

**If diff > 200 lines**: show Block 1 + file list only, then ask "Show full diff? (yes / no)".

Ask: **"Accept these changes? (yes / review more / cancel)"**
- "review more" → show specific file or hunk the user asks about
- "cancel" → `git checkout -- .` to revert, return to issue list
