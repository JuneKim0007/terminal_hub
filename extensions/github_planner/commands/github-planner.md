# /th:github-planner — Integrated planning flow

<!-- RULE: after any draft_issue or submit_issue call, do not narrate the result.
     Continue the planning conversation. When all planned issues are created, say:
     "Let me know any plans for this!" -->

You are in **github-planner** mode — the integrated flow that orchestrates
analysis, planning, and issue creation through natural conversation.
Sub-commands handle each step; this command composes them.

---

## Step 1 — Workspace + auth check

Call `get_setup_status`.
- `initialised: false` → run the **setup sub-command** workflow (`/th:github-planner/setup`)
- `initialised: true` → continue

---

## Step 2 — Repo identification

Check `get_setup_status` result:
- `github_repo` is set → skip to Step 3 (already configured)
- `github_repo` is null → ask:

> Do you have a GitHub repo for this project?
> a) Yes — give me the URL or `owner/repo`  b) Not yet — create one for me  c) Skip, I'll work locally for now

- **(a)**: call `setup_workspace(github_repo=...)`. Store `set_preference("github_repo_connected", True)`.
- **(b)**: → follow **New-repo path + repo creation** below
- **(c)**: call `setup_workspace()` (local-only). Store `set_preference("github_repo_connected", False)`.

### New-repo path (#83)

When the user selects (b) from Step 2 — user wants a repo created, or `get_session_header` returns `{docs: false}` and no repo is configured:

1. Ask conversationally (one message, keep it casual):
   > "Tell me about your project idea — what are you building? Do you have any specific tech stacks in mind? (totally optional!)"

2. From the conversation, draft a minimal `project_summary.md` stub using this structured format:

   ```
   **Tech Stack:** <stack, or "TBD" if not mentioned>
   **Goal:** <one-sentence goal>
   **Notes:** <any constraints, deployment targets, or "TBD">
   ```

   If the user didn't mention a tech stack, suggest 2–3 sensible options that fit their idea alongside the sketch.

3. Show the sketch before saving — keep it conversational:
   > "Here's your project sketch:
   >
   > **Tech Stack:** FastAPI (Python), React (TBD)
   > **Goal:** REST API backend with a frontend and local-first deployment
   > **Notes:** Cloud deployment optional later
   >
   > Does this look right? You can confirm, add anything, or just keep chatting — I won't save until you say so."

   *(Note: when you call `update_project_description`, Claude Code will show the MCP tool call in its UI — that's normal and expected, not an error.)*

4. Wait for explicit confirmation before calling `update_project_description(content=...)`.
   If the user wants changes, revise the sketch and show it again. Do not rush to save.

5. After saving, offer to create the GitHub repo (if not already done in Step 2):
   > "Want me to create a GitHub repo for this? I'll use your project name and description.
   > Should it be public or private? (or skip if you want to set that up yourself)"

   - If user wants one created: call `create_github_repo(name=..., description=..., private=...)`
     On success: repo is linked, call `set_preference("github_repo_connected", True)`
   - If user skips: call `set_preference("github_repo_connected", False)` and continue

7. Ask once about confirmation preference:
   > "One quick thing — when I update your project design notes in the future (after new features or architecture changes), should I always ask you first, or just do it silently?
   > (always ask / just do it)"

   - "always ask" → call `set_preference("confirm_arch_changes", True)`
   - "just do it" → call `set_preference("confirm_arch_changes", False)`

8. Ask: "Want me to break your first features into issues? (yes / describe features first)"
9. On yes: continue to Step 5 (planning conversation) — skip analysis entirely.
10. Issue creation uses standard Step 6 flow with confirmation hook (#82).

---

## Step 3 — Project docs check

Call `get_session_header` (if available) or `docs_exist`.
- Docs < 7 days old → "I have project notes from {N}h ago. Use them, or re-analyze?"
- Docs ≥ 7 days or missing → recommend the **analyze sub-command** workflow

If re-using existing docs → skip to Step 5.
If analyzing → run the **analyze sub-command** workflow (`/th:github-planner/analyze`).

---

## Step 4 — Load summary (silent)

Call `load_project_docs(doc="summary")`. Absorb silently — do not show to user.
Note the `Feature Sections` line in the summary: this is the index of available
detail sections. Load individual sections via `lookup_feature_section` only when
the user discusses a topic that matches a section heading.

---

## Step 5 — Planning conversation

Say: **"Let me know any plans for this!"**

- Use project summary as background context (silent)
- When the user describes a feature or task:
  - If `session_header.sections` (or `docs_exist.sections`) contains a matching area,
    call `lookup_feature_section(feature="{area}")` and use the returned
    `section` to inform issue scope and AC.
  - Do NOT load `project_detail.md` in full — always use `lookup_feature_section`
    with a specific feature name.
- Ask one clarifying question at a time
- Propose a breakdown when the user describes enough: epics → issues
- When ready, show a one-line preview list:
  ```
  • [feat] Add OAuth refresh
  • [bug] Fix cache race condition
  Create these? (yes / edit / cancel)
  ```

---

## Step 6 — Issue creation

After approval:
1. For each planned issue: call `lookup_feature_section(feature="...")` if not already
   done for that area. Use returned section + global_rules in the issue body.
2. For each issue, generate `agent_workflow` steps — **always required, never omit**:
   - Step 1: `"Scan all files and cache the project file structure"`
   - Step 2: `"Build a temporary knowledge base — group relevant files (Group A) vs unrelated (Group B)"`
   - Steps 3–N: specific to this issue's requirements
   - Final step: `"Verify full test suite passes and acceptance criteria are met"`
3. Call `draft_issue(title, body, labels, assignees, agent_workflow=[...])` for each — **silent**
3. Show confirmation block before any GitHub call (#82):
   ```
   About to: Create {N} GitHub issues on {repo}
     {issue-1-title} [{labels}]
     {issue-2-title} [{labels}]
     ...
   Proceed? (yes / review first / cancel)
   ```
   Wait for explicit "yes" before continuing.
4. If yes: call `submit_issue(slug)` for each — **silent**
5. **Auto-update project docs** — use the label-based decision table below.
   Do **not** use LLM inference on title text; only labels are authoritative.

   Before updating docs, check the `confirm_arch_changes` preference:
   - If `confirm_arch_changes = true` (or unknown/unset): show a one-line preview and ask
     "Update project notes to include this feature? (yes/no)" before calling any update tool.
   - If `confirm_arch_changes = false`: update silently, no prompt needed.

   | Labels on the batch | Action |
   |---------------------|--------|
   | Any issue has `enhancement` or `feature` | Call `update_project_detail_section(feature_name, content)` to merge a new or updated section. Do **not** rewrite the full file. |
   | Any issue has `architecture` | Update `project_summary.md` Design Principles section via `update_project_detail_section`. |
   | All labels are `bug`, `chore`, `refactor`, or `docs` | **No doc update** — zero extra API calls. |
   | No labels set | Ask user: "This looks like a new feature — should I add it to the design dictionary? (yes/no)" — then follow appropriate row above. |

   `update_project_detail_section(feature_name, content)` merges a single H2 section
   into `project_detail.md` without rewriting the rest of the file.
6. **Offer context cleanup:**
   Ask: "Planning done! Unload cached data to keep Claude's context lean? (yes/no)"
   - If yes: call `apply_unload_policy(command="github-planner")` — this reads
     `unload_policy.json` and clears only what's in `unload[]` for this command.
     Repo config, preferences, and all disk docs/issues are always preserved.
     Print `_display` from the result.
   - If no: proceed.
7. Say: **"Let me know any plans for this!"**

---

## Sub-commands available independently

| Command | Say | Does |
|---------|-----|------|
| `/th:github-planner/list-issues` | "list issues" | Show issue table |
| `/th:github-planner/create-issue` | "create an issue" | Single guided issue |
| `/th:github-planner/analyze` | "analyze my repo" | Build project docs |
| `/th:github-planner/setup` | "set up github" | Workspace init |
| `/th:github-planner/auth` | "fix auth" | Auth recovery |
