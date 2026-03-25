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

## Step 1 — Context switch (silent)

Call `set_project_root(path="<Claude's actual working directory>")` first — this ensures hub_agents/ is written to the user's project.
Call `apply_unload_policy(command="gh-implementation")`.
Output `_display` verbatim as a **standalone line** — nothing before or after it on the same line.
Do NOT bury it in a sentence. Example output line: `🧹 Cleared: analysis_cache, label_cache`

**Skill setup (once per session):** If `hub_agents/skills/` does not exist, prompt once:
> "I can load a skills index for this project to guide my behaviour.
> Do you have one? (point me to the path / create a starter for me / skip)"
> - **point me to path** → call `connect_docs(skills="<path>")`
> - **create a starter** → generate `hub_agents/skills/SKILLS.md` and call `connect_docs(skills="hub_agents/skills/SKILLS.md")`
> - **skip** → proceed; only plugin-level skills (Tier 1) will be used

**Persistent skills:** `set_project_root` triggers `_load_skill_registry` — skills with `alwaysApply: true` are auto-available.

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

Call `load_active_issue(slug)` — this is **mandatory**. Do not read the issue file separately.

- The returned `agent_workflow` field is the authoritative workflow (no frontmatter re-read needed)
- The returned `content` is the full issue context — it is already in your context window
- **`agent_workflow` present in return value** → go to Step 6 (implement)
- **`agent_workflow` absent** → go to Step 5 (define workflow)

**Design refs:** If the loaded issue has `design_refs` in its frontmatter, use those as the
lookup targets — call `lookup_feature_section(feature="<section>")` for each
`project_detail.md § <section>` entry. Do **not** do a broad doc scan; the refs already
identify the relevant sections. If no `design_refs` are present, fall back to checking
`project_detail.md` for any feature section matching this issue's area.

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

## Step 6.6a — Failure handling

**On any failure from Step 6.6** (failed tests OR coverage < threshold):

1. Write `hub_agents/cache/test_failures.json`:
   ```json
   {
     "issue_slug": "<active slug>",
     "affected_files": [...],
     "failed_tests": ["test_name", ...],
     "coverage": <float>,
     "threshold": <int>,
     "errors": ["AssertionError: ...", ...]
   }
   ```
   Extract `failed_tests` and `errors` by parsing FAILED/ERROR lines from `filtered_output`.

2. Classify failure type from error messages in `filtered_output`:
   - Contains `ImportError` or `ModuleNotFoundError` → `import_error`
   - Contains `AssertionError` → `assertion_error`
   - No FAILED lines but `coverage < threshold` → `missing_coverage`
   - Multiple types or unrecognised → `general`

3. Load suggestion file:
   - Check `extensions/gh_management/gh_implementation/suggestions/{failure_type}.md`
   - If not found → load `extensions/gh_management/gh_implementation/suggestions/general.md`
   - Use Read tool to load the file.

4. Present to user (one message):
   ```
   ⚠ {N} tests failed / coverage {X}% (threshold: {Y}%)

   Suggested fix:
   {suggestion file content}
   ```
   Then call `format_prompt(question="What would you like to do?", options=["fix", "skip", "set new threshold"], style="question")` and print `_display`.

5. Handle user response:
   - **fix** → apply the minimal fix described in the suggestion to the affected files, then re-run Step 6.6 (call `run_tests_filtered(files=affected_files)` again). If it passes, continue to Step 7. If still failing, show updated results and ask again.
   - **skip** → continue to Step 7 with a note: `(tests have failures — accepted by user)`
   - **set new threshold** → ask "New threshold? (integer 0–100)", validate, then replace the `COVERAGE_THRESHOLD = <N>` line in `terminal_hub/constants.py` using Edit tool. Confirm: `COVERAGE_THRESHOLD = {new} (was {old}) — saved`. Then re-run Step 6.6.

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
