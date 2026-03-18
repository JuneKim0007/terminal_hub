# /th:gh-implementation — Issue Implementation Flow

<!-- RULE: after any implementation action, do not narrate results verbosely.
     Present diffs clearly, ask for acceptance, then proceed. -->

You are in **gh-implementation** mode — the end-to-end flow for implementing a tracked GitHub issue.

---

## Step 1 — Context switch (silent)

Call `apply_unload_policy(command="gh-implementation")`.
This unloads gh_planner analysis caches and keeps project_summary.md and project_detail.md.
Do not narrate this.

---

## Step 2 — Read project context (silent)

Call `load_project_docs(doc="summary")` — absorb silently.
This gives you design principles and tech stack.
Do not read project_detail.md in full — use `lookup_feature_section` per topic when needed.

---

## Step 3 — Load issues

Call `list_issues`. If issues are returned: show a compact numbered list and ask:
> "Which issue would you like to implement? (number or title)"

If no local issues:
> "No local issues found. Options:
> a) Switch to planner mode (/th:github-planner) to create some
> b) Fetch issues from GitHub and sync them locally"

- **(a)**: say "Run `/th:github-planner` to plan and track issues."
- **(b)**: call `fetch_github_issues()` (TODO #125) to pull open issues from GitHub

---

## Step 4 — Load selected issue

Read the chosen issue file. Check for `agent_workflow` in front matter.

- **`agent_workflow` present** → go to Step 6 (implement)
- **`agent_workflow` absent** → go to Step 5 (define workflow)

Also check `project_detail.md` for any feature section matching this issue's area.
Use `lookup_feature_section(feature="...")` if relevant.

---

## Step 5 — Define agent workflow (if missing)

If issue has no `agent_workflow`, derive one from:
- Issue title, body, labels
- Matching feature section from project_detail.md
- Design principles from project_summary.md

Steps 1–2 are always:
1. "Scan all files and cache the project file structure"
2. "Build a temporary knowledge base — group relevant files (Group A) vs unrelated (Group B)"
Then add issue-specific steps.

Call `draft_issue` or update the issue file to persist the workflow before proceeding.

---

## Step 6 — Implement

Follow the `agent_workflow` steps in order. After each logical change:
- Run tests if applicable
- Do not ask the user unless blocked

When implementation is complete → go to Step 7.

---

## Step 7 — Present changes

Show a summary of what changed, then present a human-readable diff:

```
Changes for issue #{slug}: {title}

Files modified:
  M  src/auth.py        (+24 / -3)
  A  tests/test_auth.py (+41)

Diff summary:
[human-readable description of what changed and why]

--- git diff excerpt ---
{key hunks only — omit noise}
```

Ask: **"Accept these changes? (yes / review more / cancel)"**

---

## Step 8 — Push and close

If accepted:
1. Check `close_automatically_on_gh` session flag (from `get_implementation_session`)
2. If `true`: commit, push, close GitHub issue — **after confirming** if this is the first time this session:
   > "About to: commit, push, and close issue #{number} on GitHub. Proceed? (yes / yes, don't ask again this session)"
   - "yes, don't ask again" → set session flag and proceed automatically for remaining issues
3. If `false`: commit and push only, leave issue open

---

## Step 9 — Cleanup

Ask: **"Remove local issue file hub_agents/issues/{slug}.md? (yes / no / yes, never ask again)"**
- "yes, never ask again" → set `delete_local_issue_on_gh = false` in session (suppress future prompts)

---

## Sub-commands

| Command | Does |
|---------|------|
| `/th:gh-implementation/implement` | Run Steps 3–9 for a specific issue |
| `/th:gh-implementation/session-knowledge` | View or change session flags |
