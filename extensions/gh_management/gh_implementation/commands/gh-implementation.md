# /th:gh-implementation — Issue Implementation Flow

<!-- RULE: WORKSPACE ROOT — always call set_project_root(path=<cwd>) as the very first tool call so hub_agents/ is written to the user's project, not the MCP server's directory. -->

<!-- RULE: CONNECTED DOCS — after load_project_docs(), check if _display mentions a primary
     ref (e.g. "`DESIGN.md` (primary ref)"). If yes, the primary reference content was
     already merged into the summary — no extra load needed.
     For other_references, use load_connected_docs(section="...") when the issue topic
     matches a section heading in that reference doc. -->

<!-- RULE: after any implementation action, do not narrate results verbosely.
     Present diffs clearly, ask for acceptance, then proceed. -->

<!-- RULE: FILE LOADING — lazy and partial. Never load a file as a routine step.
     Only load when you have decided it is relevant to the current issue.
     Fetch only the needed section (lookup_feature_section, not full file).
     load_project_docs(summary) at Step 2 is the only unconditional load. -->

<!-- RULE: TASK DISPATCH — match model to task weight.
     File-location / scan / classification → dispatch_task (Haiku).
     Simple writes to disk → Python MCP call directly.
     Analysis / implementation planning → current model (Sonnet). -->

<!-- RULE: for every yes/no or choice prompt shown to the user, call
     format_prompt(question, options, style) first and print _display verbatim.
     styles: "question" (default), "confirm", "warning", "switch", "error" -->

<!-- LOAD ANNOUNCEMENT: At the very start of this command, output exactly:
     🟢 Loaded: gh-implementation — `extensions/gh_implementation/commands/gh-implementation.md`
     Do this before any tool calls. -->

You are in **gh-implementation** mode — the end-to-end flow for implementing a tracked GitHub issue.

---

## Mode switching — bidirectional (always active)

Detect planning intent at any point during the conversation. Signals include:
- "I want to add a feature / create an issue / plan something"
- "what should I work on next", "let me think about what to build"
- "can we plan X", "I have an idea for Y"
- User describes a new requirement without referencing an existing issue

**Session flag: `auto_switch_modes`**

- **Not set (first time):** Ask once:
  > "Sounds like you want to plan — switch to /th:gh-plan? (yes / no / yes, don't ask again)"
  - "yes, don't ask again" → set `auto_switch_modes = true` in session via `set_implementation_session_flag`
  - "yes" → switch (ask next time)
  - "no" → stay in implementation mode

- **`auto_switch_modes = true`:** Switch silently — just print one line:
  > `→ Switching to planning mode`
  Then apply unload + load gh-plan. No offer shown.

**On switch:**
1. Call `apply_unload_policy(command="gh-implementation")` — print `_display`
2. Invoke `/th:gh-plan` skill — that command takes over from Step 1

Do NOT show the switch offer again after the user has already said yes in this session.

---

## Step 1 — Context switch (silent)

Call `set_project_root(path="<Claude's actual working directory>")` first — this ensures hub_agents/ is written to the user's project.
Call `apply_unload_policy(command="gh-implementation")`.
Output `_display` verbatim as a **standalone line** — nothing before or after it on the same line.
Do NOT bury it in a sentence. Example output line: `🧹 Cleared: analysis_cache, label_cache`

**Repo confirmation (#148):** Call `confirm_session_repo()`.
- `confirmed: true` → proceed silently
- `confirmed: false` → print `_display` verbatim and ask "yes / change" (same flow as gh-plan Step 1)

---

## Step 2 — Read project context (silent)

Call `load_project_docs(doc="summary")`. Print `_display` verbatim (e.g. "📄 Loaded: project_summary.md (1,234 bytes)"). Do not show the doc contents.
Do not read project_detail.md in full — use `lookup_feature_section` per topic when needed.

---

## Step 3 — Load issues

Call `list_issues`. If issues are returned: show a compact numbered list and ask:
> "Which issue would you like to implement? (number or title)"

If no local issues:
> "No local issues found. Options:
> a) Switch to planner mode (/th:gh-plan) to create some
> b) Fetch issues from GitHub and sync them locally"

- **(a)**: say "Run `/th:gh-plan` to plan and track issues."
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

First infer the issue's size from its labels and scope:

**If `dispatch_task` tool is available** (plugin_customization loaded):
  Call `dispatch_task(task_type="issue_classification", prompt="{title}\n\n{body excerpt}")`.
  Use the returned `size` directly.

**Otherwise** (fallback): infer size manually — trivial / small / medium / large — same rules as gh-plan Step 6a.

- **trivial** → no workflow needed; just make the change
- **small** → `"Skim the relevant file(s), check for existing patterns, make the fix."` + 1–2 specific steps
- **medium/large** → orientation step:
  `"Orient yourself as an experienced developer picking up this task. If dispatch_task is available: call dispatch_task('structure_scan', file_tree_content) to get an area map, and call dispatch_task('file_location', issue_title + body) to get relevant files — use results to inform your concrete plan. Otherwise: if project docs exist (project_summary.md, project_detail.md), scan their headings — read only sections relevant to this area; if no docs, list files and filter by relevance. Stop once you have enough context. State your concrete plan: what you'll change, where, in what order, and what to watch for."`
  Then add issue-specific steps for 2–N.

Do NOT prescribe which files to read — let the agent decide based on the issue.

Call `draft_issue` or update the issue file to persist the workflow before proceeding.

---

## Step 6 — Implement

Follow the `agent_workflow` steps in order. After each logical change:
- Run tests if applicable
- Do not ask the user unless blocked

When implementation is complete → go to Step 7.

---

## Step 7 — Present changes

Run `git diff HEAD` (Bash tool), then present in two blocks — never dump raw patch:

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

If diff > 200 lines: show Block 1 + file list only, then ask "Show full diff? (yes / no)".

Ask: **"Accept these changes? (yes / review more / cancel)"**
- "review more" → show specific file or hunk the user asks about
- "cancel" → `git checkout -- .` to revert, return to issue list

---

## Step 8 — Push and close

If accepted:
1. Check `close_automatically_on_gh` session flag (from `get_implementation_session`)
2. If `true`: commit, push, close GitHub issue — **after confirming** if this is the first time this session:
   > "About to: commit, push, and close issue #{number} on GitHub. Proceed? (yes / yes, don't ask again this session)"
   - "yes, don't ask again" → set session flag and proceed automatically for remaining issues
3. If `false`: commit and push only, leave issue open

---

## Step 9 — Post-ship doc sync

After pushing and closing, update project docs to reflect what was actually built.
Read the closed issue's labels from its local file frontmatter, then apply this table:

| Labels | Action |
|--------|--------|
| Any `enhancement` or `feature` | Call `update_project_detail_section(feature_name, content)` — merge/update the feature section to reflect what was shipped. Include `**Milestone:** Mx — Name` at the top if milestones are in use. |
| Any `architecture` | Call `update_project_summary_section(section_name="Design Principles", content=...)` |
| All `bug`, `chore`, `refactor`, or `docs` | **No doc update** — skip entirely |
| No labels | Ask: "Should I update the design notes for this? (yes/no)" — then follow the appropriate row above |

Before writing, check `confirm_arch_changes` preference:
- `true` or unset → show a one-line preview and ask "Update project notes? (yes/no)" before calling any update tool
- `false` → update silently

---

## Step 10 — Cleanup

Ask: **"Remove local issue file hub_agents/issues/{slug}.md? (yes / no / yes, never ask again)"**
- "yes, never ask again" → set `delete_local_issue_on_gh = false` in session (suppress future prompts)

---

## Sub-commands

| Command | Does |
|---------|------|
| `/th:gh-implementation/implement` | Run Steps 3–10 for a specific issue |
| `/th:gh-implementation/session-knowledge` | View or change session flags |
