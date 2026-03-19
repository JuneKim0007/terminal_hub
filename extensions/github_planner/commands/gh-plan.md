# /th:gh-plan — Integrated planning flow

<!-- RULE: after any draft_issue or submit_issue call, do not narrate the result.
     Continue the planning conversation. When all planned issues are created, say:
     "Let me know any plans for this!" -->

<!-- RULE: for every yes/no or choice prompt shown to the user, call
     format_prompt(question, options, style) first and print _display verbatim.
     styles: "question" (default), "confirm", "warning", "switch", "error" -->

<!-- LOAD ANNOUNCEMENT: At the very start of this command, output exactly:
     🟢 Loaded: gh-plan — `extensions/github_planner/commands/gh-plan.md`
     Do this before any tool calls. -->

You are in **gh-plan** mode — the integrated flow that orchestrates
analysis, planning, and issue creation through natural conversation.
Sub-commands handle each step; this command composes them.

---

## Step 1 — Workspace + auth check

Call `get_setup_status`.
- `initialised: false` → run the **setup sub-command** workflow (`/th:gh-plan-setup`)
- `initialised: true` → continue

**Repo confirmation (#148):** If `github_repo` is set, call `confirm_session_repo()`.
- `confirmed: true` → proceed silently (already confirmed this session)
- `confirmed: false` → print `_display` verbatim, then ask user "yes / change":
  - "yes" → call `set_session_repo(repo=...)` to lock it, then proceed
  - "change" → ask "Which repo? (owner/repo)", then call `set_session_repo(repo=new_repo)`

After confirmation: call `list_repo_labels()` and `list_milestones()` silently.
This warms both caches so `submit_issue`/`assign_milestone` never make cold API calls,
and gives Claude the repo's actual label and milestone names for planning (Step 5/6).
If either call fails with 404 or auth error, surface it immediately — bad repo config
should be caught here, not at submit time.

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

   ## Design Principles
   - <Architectural style — e.g. "layered: routes → services → storage">
   - <Key convention — e.g. "all public functions must have type hints">
   - <Non-negotiable rule — e.g. "no mutable global state outside MCP server init">
   - <Test policy — e.g. "coverage ≥ 80%; no merging with failing tests">
   ```

   If the user hasn't described conventions yet, use sensible defaults for their stack
   and mark them `(default — update anytime)`. Agents implementing issues MUST read
   Design Principles before touching any code.

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

## Step 2.5 — Milestone derivation (after project summary is saved)

**Check `milestone_assign` preference first** via `read_preference("milestone_assign")`:
- If `True`: skip the question, go directly to deriving and creating milestones
- If `False`: skip milestones entirely this session
- If unset (None): proceed with the question below

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

- **"yes"** → call `create_milestone()` for each; cache results → then persist to project_summary.md (see below)
- **"yes, always"** → call `create_milestone()` + `set_preference("milestone_assign", True)` → persist to project_summary.md
- **"no"** → proceed without milestones; no further milestone prompts this session; call `set_preference("milestone_assign", False)`

**After creating milestones**, call `update_project_summary_section(section_name="Milestones", content=...)` to persist the milestone table. Use this format for the content:
```
| # | Name | Delivers |
|---|------|---------|
| M1 | Core Auth | Users can sign up, log in, and reset their password |
| M2 | Posting | Authenticated users can create, edit, and delete posts |
| M3 | Launch Polish | Performance, error handling, and deploy pipeline complete |
```
This is the authoritative milestone reference for agents implementing issues — they MUST check this section before asking "which milestone does this belong to?".

**Cache note:** Milestones are pre-fetched in Step 1 and live in `_MILESTONE_CACHE`. Do NOT call `list_milestones()` again — use the cached data for issue assignment.

---

## Step 3 — Project docs check

Call `get_session_header` (if available) or `docs_exist`.
- Docs < 7 days old → "I have project notes from {N}h ago. Use them, or re-analyze?"
- Docs ≥ 7 days or missing → recommend the **analyze sub-command** workflow

If re-using existing docs → skip to Step 5.
If analyzing → run the **analyze sub-command** workflow (`/th:gh-plan-analyze`).

---

## Step 4 — Load summary (silent)

Call `load_project_docs(doc="summary")`. Print `_display` verbatim (e.g. "📄 Loaded: project_summary.md (1,234 bytes)"). Do not show the doc contents.
Note the `Feature Sections` line in the summary: this is the index of available
detail sections. Load individual sections via `lookup_feature_section` only when
the user discusses a topic that matches a section heading.

Also note the `## Milestones` section if present — this is the authoritative milestone
reference. Use it to determine which milestone an issue belongs to without calling
`list_milestones()`. Example: "Feature X → M2 — Posting".

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
- **Label suggestions:** use names from `_LABEL_CACHE` (warmed in Step 1). Never invent
  a label not in cache or `labels.json`. Suggest type label (`bug`/`feature`/`enhancement`/
  `refactor`/`chore`/`documentation`/`performance`) + area label if identifiable.
- **Milestone suggestions:** if exactly one active milestone is in `_MILESTONE_CACHE`,
  mention it as the natural target. If multiple exist, ask which one fits.
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
2b. **Auto-assign labels** — check `label_auto_assign` preference (default `true`):
   - If `true`/unset: infer labels from issue description using this table (only use names in `_LABEL_CACHE` or `labels.json`):
     | Condition | Label |
     |-----------|-------|
     | Crash / incorrect behaviour / regression | `bug` |
     | New user-visible capability | `feature` or `enhancement` |
     | Code cleanup, no behaviour change | `refactor` or `chore` |
     | Docs/comments only | `documentation` |
     | Speed / memory / API call improvement | `performance` |
     Also add an area label (`backend`, `frontend`, `auth`, `api`, etc.) if clearly identifiable.
   - If `false`: leave labels empty; let user specify.

2c. **Auto-assign milestone** — check `milestone_auto_assign` preference (default `true`):
   - If `true`/unset: apply the first matching rule below (stop at first match):
     1. Title/body references a version or sprint (e.g. `v2.0`, `Sprint 3`) → assign milestone whose name matches
     2. Exactly one active milestone in `_MILESTONE_CACHE` → assign it silently
     3. Multiple active milestones → ask user: "Which milestone? ({names}) / skip"
     4. No milestones → leave unassigned (do NOT create one per issue)
   - If `false`: no milestone assignment.
   - Never auto-create a milestone for an individual issue — milestones are created in Step 2.5.

3. Call `draft_issue(title, body, labels, assignees, agent_workflow=[...], milestone_number=N_or_None)` for each — **silent**
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
   | Any issue has `enhancement` or `feature` | Call `update_project_detail_section(feature_name, content)` to merge a new or updated section. Do **not** rewrite the full file. **Include `**Milestone:** Mx — Name` at the top of the section content** if milestones exist in `_MILESTONE_CACHE` or project_summary.md Milestones table. |
   | Any issue has `architecture` | Update `project_summary.md` Design Principles section via `update_project_summary_section(section_name="Design Principles", content=...)`. |
   | All labels are `bug`, `chore`, `refactor`, or `docs` | **No doc update** — zero extra API calls. |
   | No labels set | Ask user: "This looks like a new feature — should I add it to the design dictionary? (yes/no)" — then follow appropriate row above. |

   `update_project_detail_section(feature_name, content)` merges a single H2 section
   into `project_detail.md` without rewriting the rest of the file.
6. **Offer implementation** — ask immediately after issues are submitted:
   > "Implement now using /th:gh-implementation? (yes / no)"
   - **yes** → call `apply_unload_policy(command="gh-plan")` — output `_display` as a standalone line,
     then invoke `/th:gh-implementation` — this switches mode automatically.
     Do NOT ask about cache cleanup separately; the unload happens as part of the switch.
   - **no** → ask: "Unload cached data to keep context lean? (yes/no)"
     - If yes: call `apply_unload_policy(command="gh-plan")` — output `_display` as a standalone line.
     - If no: proceed.
7. Say: **"Let me know any plans for this!"**

---

## Sub-commands available independently

| Command | Say | Does |
|---------|-----|------|
| `/th:gh-plan-list` | "list issues" | Show issue table |
| `/th:gh-plan-create` | "create an issue" | Single guided issue |
| `/th:gh-plan-analyze` | "analyze my repo" | Build project docs |
| `/th:gh-plan-setup` | "set up github" | Workspace init |
| `/th:gh-plan-auth` | "fix auth" | Auth recovery |
