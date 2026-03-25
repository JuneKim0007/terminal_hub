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

## Design principle detection (always active)

If any user message at any point during implementation contains trigger phrases — "always", "never", "every time", "must always", "should always", "don't ever", "every X must", "all X should" — before responding:
1. Call `format_prompt(question="That sounds like a design principle — add it to your project docs?", options=["yes", "no"], style="confirm")` — print `_display` verbatim
2. If "yes": read `hub_agents/docs_config.json` → find entry with `primary: true` or `type: "design"` → append `- {principle text} *(added {date})*` under `## Design Principles`. Also call `update_project_summary_section(section_name="Design Principles", ...)` to append it. Confirm: `Saved: "{principle}" → {doc_path}`
3. If no connected design doc found: ask "Which file? (path / 'create new')". On "create new": create `hub_agents/design_principles.md` and call `connect_docs(design="hub_agents/design_principles.md")`
4. If "no": proceed without saving

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

## Step 1 — Pre-implementation (single call)

Call `set_project_root(path="<Claude's actual working directory>")` first — this ensures hub_agents/ is written to the user's project.

Call `pre_implementation(issue_slug=<slug>)`:
- Returns full context: project summary, active issue, design sections, connected docs, flags
- Print `_display` verbatim

If `has_agent_workflow: true` → go to Step 6 (implement)
If `has_agent_workflow: false` → go to Step 5 (define workflow)

**Skill setup (once per session):** If `hub_agents/skills/` does not exist, prompt once:
> "I can load a skills index for this project to guide my behaviour.
> Do you have one? (point me to the path / create a starter for me / skip)"
> - **point me to path** → call `connect_docs(skills="<path>")`
> - **create a starter** → generate `hub_agents/skills/SKILLS.md` and call `connect_docs(skills="hub_agents/skills/SKILLS.md")`
> - **skip** → proceed; only plugin-level skills (Tier 1) will be used

**Persistent skills:** `set_project_root` triggers `_load_skill_registry` — skills with `alwaysApply: true` are auto-available.

---

## Step 5 — Define agent workflow (if missing)

If issue has no `agent_workflow`, derive one from:
- Issue title, body, labels
- Matching feature section from project_detail.md
- Design principles from project_summary.md

<!-- SKILL: load_skill("implementing") — contains workflow derivation rules per size (trivial/small/medium/large) -->

Call `draft_issue` or update the issue file to persist the workflow before proceeding.

---

## Step 6 — Implement

Follow the `agent_workflow` steps in order. After each logical change:
- Run tests if applicable
- Do not ask the user unless blocked

When implementation is complete → go to Step 6.5.

---

## Step 6.5 — make_test (generate or update tests)

After Step 6 completes, generate targeted tests before presenting the diff.

**`make_test(files=None)` vs `make_test(files=[list])`:**
- `files=None` (default) → derive affected files from `git diff --name-only HEAD`
- `files=[list]` → use that specific subset (for targeted re-runs after a fix)

**For each affected file:**

1. Determine the test file path: `tests/test_{module}.py` for top-level modules, `tests/{subdirectory}/test_{file}.py` for nested paths. Mirror the source tree under `tests/`.

2. **Test file does not exist** → create it with full scaffold using the Write tool. The generation prompt must include:
   - The affected file's full content (read it)
   - Changed function/class signatures extracted from `git diff HEAD`
   - Issue title + body (the "why")
   - The `agent_workflow` steps (the "how")
   - Design principles from project_summary.md (coverage ≥ 80%, no mutable global state)

3. **Test file exists** → update it partially using the Edit tool. Extract only the new/changed function signatures from `git diff HEAD` — add new test cases for those signatures only. Do NOT rewrite the whole test file or touch untouched test cases.

**Note:** `write_test_file` MCP tool is plugin_creator-scoped only — use `Write`/`Edit` tools directly for test file operations here.

After make_test → go to Step 6.6 (verify).

---

## Step 6.6 — verify (run tests with filtered output)

After Step 6.5 (make_test):

1. Call `run_tests_filtered(files=affected_files)`:
   - Runs the full pytest suite internally
   - Filters output through `filter_test_results()` in `terminal_hub/utils/test_filter.py` (single export — never duplicate)
   - Returns `{passed, failed, coverage, meets_threshold, threshold, filtered_output, raw_summary}`

2. Claude reads `filtered_output` only — not the raw pytest log. This keeps context lean.

3. **If all pass and coverage ≥ threshold:**
   Print: `Tests passed — coverage {N}% ({passed} passed, 0 failed)` and continue to Step 7.

4. **If failures or coverage below threshold:**
   Go to Step 6.6a (failure handling — see #210).

**Note:** `files=None` skips filtering and returns full pytest output — use for full-suite runs.

---

## Step 6.7 — Post-implementation (single call)

After Step 6.6 (make_test + verify complete):
Call `post_implementation(issue_slug=<slug>)`:
- Returns test results, diff summary, affected files
- Print `_display` verbatim
- Show `diff.diff_text` to user (or summarize if > 200 lines)

Ask: **"Accept these changes? (yes / review more / cancel)"**
- "yes" → run `git commit -m "<type>: <description> (#<issue_number>)"` + `git push` via Bash tool
  Then if `close_automatically_on_gh=true`: call `close_github_issue(issue_number)`
  Then call `unload_active_issue()`
- "review more" → show specific file/hunk
- "cancel" → `git checkout -- .` and return to issue list

---

## Step 7 — Present changes

Run `git diff HEAD` (Bash tool), then present changes to the user.

<!-- SKILL: load_skill("implementing") — contains diff presentation format (Block 1 + Block 2) and >200 lines rule -->

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
Read the closed issue's labels from its local file frontmatter.

<!-- SKILL: load_skill("design-principles") — contains doc update decision table, label → action mapping, confirm_arch_changes behavior -->

---

## Step 10 — Cleanup

Call `unload_active_issue()` — this is **mandatory**. It clears session state and deletes the
local issue file per the `delete_local_issue_on_gh` flag (default: true).

To override deletion for this issue only: `unload_active_issue(delete_file=False)`.

**After cleanup:** call `list_issues`. If the result is empty (no remaining open issues), prompt:

> "All issues are closed. Want me to write or update docs for users and devs? (`/th:gh-docs`)"

- "yes" → invoke `/th:gh-docs`
- "no" → end the session

---

## Sub-commands

| Command | Does |
|---------|------|
| `/th:gh-implementation/implement` | Run Steps 3–10 for a specific issue |
