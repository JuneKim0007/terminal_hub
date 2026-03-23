# /th:gh-plan — Integrated planning flow

<!-- RULE: WORKSPACE ROOT — always call set_project_root(path=<cwd>) as the very first tool call so hub_agents/ is written to the user's project, not the MCP server's directory. -->

<!-- RULE: CONNECTED DOCS — at Step 4, after load_project_docs(), check if _display mentions
     a primary ref (e.g. "`DESIGN.md` (primary ref)"). If yes, the primary reference content
     was already merged into the summary — no extra load needed.
     For other_references, use load_connected_docs(section="...") when the user's topic
     matches a section heading in that reference doc. -->

<!-- RULE: after any draft_issue or submit_issue call, do not narrate the result.
     Continue the planning conversation. When all planned issues are created, say:
     "Issues drafted and submitted! Let me know if you'd like me to start implementing or if you want to change any issues!" -->

<!-- RULE: FILE LOADING — lazy and partial. Never load a file as a routine step.
     Only load when you have decided it is relevant to the current task.
     When you do load, fetch only the section you need (lookup_feature_section,
     not the full file). load_project_docs is the exception — load summary at
     Step 4 only; never load project_detail.md in full at any point. -->

<!-- RULE: TASK DISPATCH — match model to task weight.
     File-location / scan / classification → dispatch_task (Haiku).
     Simple writes to disk → Python MCP call directly (no LLM needed).
     Analysis / planning / issue body generation → current model (Sonnet).
     Never use Sonnet for mechanical lookups that Haiku can handle. -->

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

Call `set_project_root(path="<Claude's actual working directory>")` first — this ensures hub_agents/ is written to the user's project.
Then call `get_setup_status`.
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

**Milestone cache check (#49):** After `list_milestones()` completes, check `milestone_assign` preference via `read_preference("milestone_assign")`. If the preference is not `False` and `list_milestones()` returned 0 milestones, scan local issues (from `list_issues()`) for any that have a `milestone_number` set. If any are found, offer once per session:
> "Some issues have milestone assignments but no milestones exist on GitHub — fetch them? (yes / skip)"
- **yes** → call `list_milestones()` again (forces a fresh fetch); if still empty, note "No milestones found on GitHub — milestone assignments may be stale."
- **skip** → proceed without milestones; do not ask again this session.

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

<!-- PRINCIPLE CATEGORIES — reference for principle derivation in new-repo path Step 2c.
     Not shown to users. Agents: pick only categories that apply; write specific rules, not placeholders.

     API backend:
       Architecture:    layered (routes → services → repositories → DB); no direct DB calls from routes
       Performance:     lazy-load config + connections; never at import time; cache DB results keyed by (table, filter_hash), invalidate on write
       Modularity:      each feature is a self-contained module (router + service + schema); shared utilities in /core — no circular imports
       Testing:         coverage ≥ 80%; integration tests for all DB paths; no mocking the DB in integration tests
       Conventions:     all public functions have type hints; errors returned as {error: str, detail: ...}; secrets via env vars only

     CLI tool:
       Architecture:    each command is a single-responsibility function; no business logic in CLI layer
       Performance:     lazy I/O — open files only when needed; stream large outputs instead of buffering
       State:           no mutable global state; pass context explicitly
       Testing:         test command outputs via subprocess or invoke; cover exit codes 0/1/2
       Conventions:     --help on every command; exit 0 = success, exit 1 = user error, exit 2 = internal error

     Web app (full-stack):
       Architecture:    component owns its data fetching; no prop drilling beyond 2 levels — use context or store
       SSR/CSR:         data fetched server-side for SEO-critical pages; client-side for interactive widgets
       Validation:      validate at API boundary; never trust client-supplied data
       Testing:         unit test components in isolation; E2E for critical user journeys
       Conventions:     co-locate styles with components; no inline styles in JSX

     Data pipeline:
       Architecture:    each stage is idempotent; pipelines are restartable from any checkpoint
       Data integrity:  schema validated at ingestion boundary; no silent data loss — log + halt on schema mismatch
       Performance:     process in chunks; never load full dataset into memory
       Testing:         test each transform in isolation with fixture data; test full pipeline with small synthetic dataset

     Library / SDK:
       Architecture:    stable public API; internals may change freely
       Side effects:    no side effects at import time; no global state mutations
       Versioning:      semver — breaking changes only in major versions
       Testing:         100% coverage of public API; document + test edge cases explicitly

     MCP server / agent tooling:
       Architecture:    each tool has one responsibility; no tool modifies state without returning confirmation
       Performance:     lightweight tool calls in hot paths; avoid re-reading files already in context
       Caching:         cache keys are deterministic strings; lookups return structured objects not raw strings; invalidate on mutation
       Conventions:     every tool returns _display for UI rendering; errors returned as {error: str}, never raised raw
-->

### New-repo path (#83)

When the user selects (b) from Step 2 — user wants a repo created, or `get_session_header` returns `{docs: false}` and no repo is configured:

1. Ask conversationally (one message, keep it casual):
   > "Tell me about your project idea — what are you building? Do you have any specific tech stacks in mind? (or just tell me your general workflow)"

2. **Classify, derive, and confirm** — before drafting or saving anything:

   **a. Classify project type** from the description — pick the closest:
   - API backend (FastAPI / Express / Rails / Spring / etc.)
   - CLI tool
   - Web app (full-stack or frontend-only)
   - Data pipeline / ETL
   - Library / SDK
   - MCP server / agent tooling
   - Other — describe

   **b. Tech stack** — if the user didn't mention one, suggest 2–3 sensible options with a one-line rationale each and ask which to use. Wait for their answer before deriving principles. If they did mention a stack, confirm it.

   **c. Derive principles** by category, tailored to the classified type and confirmed stack. Use the `<!-- PRINCIPLE CATEGORIES -->` reference table in this file. Rules:
   - Include only categories that apply to this project type (4–6 principles total — not a laundry list)
   - Every principle must be **specific and actionable**, never boilerplate or placeholder text
   - Express constraints as rules an implementing agent can apply: "cache DB results keyed by (table, filter_hash); invalidate on write" not "use caching"
   - If a category has no strong opinion yet, omit it rather than filling it with generic text

   **d. Present the derived stack + principles** to the user before saving anything:
   > "Based on your description, here's what I'd build around:
   >
   > **Project type:** <classified type>
   > **Stack:** <confirmed or suggested stack>
   >
   > **Design Principles:**
   > Architecture:
   > - <derived architecture principle>
   >
   > Performance:
   > - <derived performance principle, if applicable>
   >
   > Testing:
   > - <derived test policy>
   >
   > Conventions:
   > - <derived convention>
   >
   > Does this match how you want to build? Confirm, edit, or add anything."

   Wait for explicit confirmation or edits. Revise and re-present if needed. Do not call `update_project_description` until the user says it looks right.

3. Draft the `project_summary.md` stub using the confirmed values:

   ```
   **Tech Stack:** <confirmed stack>
   **Goal:** <one-sentence goal>
   **Notes:** <any constraints, deployment targets, or "TBD">

   ## Design Principles
   - <derived architecture principle>
   - <derived performance/caching principle, if applicable>
   - <derived modularity principle, if applicable>
   - <derived test policy>
   - <derived convention>
   ```

   Agents implementing issues MUST read Design Principles before touching any code.

   *(Note: when you call `update_project_description`, Claude Code will show the MCP tool call in its UI — that's normal and expected, not an error.)*

4. Wait for explicit confirmation before calling `update_project_description(content=...)`.
   If the user wants changes, revise the sketch and show it again. Do not rush to save.

5. **Hot path — GitHub repo creation** (ask immediately after saving, before anything else):
   > "Want me to create a GitHub repo for this now? I'll set it up, push an initial commit, and link it — you'll be ready to track issues straight away.
   > **public / private / skip**"

   - **public** or **private** → run all of these in sequence:
     1. `create_github_repo(name=<project-slug>, description=<one-line goal>, private=<bool>)`
     2. `setup_workspace(github_repo=<owner/repo>)`
     3. `set_preference("github_repo_connected", True)`
     4. `set_session_repo(repo=<owner/repo>)` — lock for this session
     5. `list_repo_labels()` + `list_milestones()` — warm caches
     Then confirm: "✅ Repo created and linked — `<owner/repo>`"
   - **skip** → call `set_preference("github_repo_connected", False)` and continue

   > "One quick thing — when I update your project design notes in the future (after new features or architecture changes), should I always ask you first, or just do it silently?
   > (always ask / just do it)"

   - "always ask" → call `set_preference("confirm_arch_changes", True)`
   - "just do it" → call `set_preference("confirm_arch_changes", False)`

7. Ask: "Want me to break your first features into issues? (yes / describe features first)"
8. On yes: continue to Step 5 (planning conversation) — skip analysis entirely.
9. Issue creation uses standard Step 6 flow with confirmation hook (#82).

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

**Sequential planning preference:**
Check `sequential_milestone_planning` preference via `read_preference("sequential_milestone_planning")`.
- `True`: after submitting all issues for a milestone, automatically ask:
  > "M{n} issues submitted. Implement now or plan M{n+1}? (implement / plan next / done)"
  - "implement" → switch to /th:gh-implementation
  - "plan next" → call `generate_milestone_knowledge(n+1)` then continue Step 5 for next milestone
  - "done" → offer unload
- `False` or unset: no prompt (existing behavior)

**Interface Layers derivation (after milestones are saved):** Check if `## Interface Layers` already exists in project_summary.md. If absent, derive 2–5 architectural layers from the tech stack and feature groups. Show compact table:
```
Proposed interface layers:
  L1 — {name}: {what lives here — 1 sentence}
  L2 — {name}: {what lives here}
  ...

Save these? (yes / customize / skip)
```
- **yes** → `update_project_summary_section(section_name="Interface Layers", content=...)` using format:
  ```
  | Layer | Description |
  |-------|-------------|
  | {name} | {description} |
  ```
- **customize** → show the proposed table, wait for edits, then save
- **skip** → proceed (issues will omit the Interface Layers line)

Interface Layers are the authoritative record of your architecture's vertical slices.
Agents read this section to know which files/modules belong to each layer before implementing.

---

## Step 3 — Project docs check

Call `get_session_header` (if available) or `docs_exist`.
- Docs < 7 days old → "I have project notes from {N}h ago. Use them, or re-analyze?"
- Docs ≥ 7 days or missing → recommend the **analyze sub-command** workflow

If re-using existing docs → skip to Step 5.
If analyzing → run the **analyze sub-command** workflow (`/th:gh-plan-analyze`).

Also check: does `load_project_docs` `_display` mention a primary reference? If yes, it was
already loaded and merged into the summary. If the user asks about a topic matching an
`other_reference`, call `load_connected_docs(section="...")` to fetch that section.

---

## Step 4 — Load summary + issue landscape (silent)

Call `load_project_docs(doc="summary")`. Print `_display` verbatim (e.g. "📄 Loaded: project_summary.md (1,234 bytes)"). Do not show the doc contents.
Note the `Feature Sections` line in the summary: this is the index of available
detail sections. Load individual sections via `lookup_feature_section` only when
the user discusses a topic that matches a section heading.

Also note:
- `## Milestones` section if present — authoritative milestone reference (do NOT call `list_milestones()` again)
- `## Interface Layers` section if present — authoritative layer reference; used in issue bodies and doc updates
- `## Planned Features` section if present — running table of all tracked issues

Call `list_issues` silently. Store the result as `_ISSUE_LANDSCAPE` — the full set of
tracked issues (slug, title, labels, milestone_number, status). Use in Step 5 to detect
scope overlap and in Step 6 to populate per-issue sibling context.

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
  - **Overlap check:** scan `_ISSUE_LANDSCAPE` for existing issues with similar title or
    feature area. If found, surface it before planning: "This looks similar to #{slug} —
    {title}. Extend that issue, or create a new one?" Do not silently duplicate.
- **Label suggestions:** use names from `_LABEL_CACHE` (warmed in Step 1). Never invent
  a label not in cache or `labels.json`. Suggest type label (`bug`/`feature`/`enhancement`/
  `refactor`/`chore`/`documentation`/`performance`) + area label if identifiable.
- **Milestone suggestions:** if exactly one active milestone is in `_MILESTONE_CACHE`,
  mention it as the natural target. If multiple exist, ask which one fits.
- Ask one clarifying question at a time
- Propose a breakdown when the user describes enough: epics → issues
- When ready, show a one-line preview list — **include milestone target if assigned**:
  ```
  • [feat] Add OAuth refresh  → M2 — Posting
  • [bug] Fix cache race condition  → M1 — Core Auth
  Create these? (yes / edit / cancel)
  ```

---

## Step 6 — Issue creation

After approval:

### 6a — Classify each issue by size

**If `dispatch_task` tool is available** (plugin_customization loaded):
  Call `dispatch_task(task_type="issue_classification", prompt="{title}\n\n{body excerpt}")`.
  Use the returned `size` directly — skip the manual sizing table below.

**Otherwise** (fallback): apply sizing rules manually using the first matching rule:

| Size | Signal | agent_workflow | AC bullets |
|------|--------|----------------|------------|
| **trivial** | `chore`/`docs`/`refactor` only; single-file, no logic change | omit entirely | 1 line |
| **small** | Isolated bug fix or single-focus change | orientation step + 1–2 specific steps | 1–3 bullets |
| **medium** | New capability, 2–5 files touched | orientation + 3–5 steps | 3–5 bullets |
| **large** | Cross-cutting, new subsystem, multiple areas | orientation + 5+ steps | 5+ bullets |

If size is ambiguous, pick the smaller bucket — err on the side of less.

### 6b — Feature section lookup (medium/large only)

For **medium** and **large** issues with a milestone assigned:
1. **First**, call `load_milestone_knowledge(milestone_number=N)` if the issue has a milestone.
   - If the knowledge file exists: use its `## Interface Contract` section as the primary context for Planning Context (Step 6c). Skip `lookup_feature_section` for this issue — the knowledge file already contains the relevant contract.
   - If no knowledge file exists (tool returns empty or error): fall back to `lookup_feature_section(feature="...")` for that area, using the returned section + global_rules in the issue body.

For **medium** and **large** issues with **no milestone**: call `lookup_feature_section(feature="...")` if not already done for that area. Use returned section + global_rules in the issue body.

Skip both for trivial/small — the overhead isn't worth it.

### 6c — Planning Context block

Append to each issue body (**omit entirely for trivial issues**):

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

<!-- If knowledge file absent, use _MILESTONE_CACHE title + _ISSUE_LANDSCAPE for siblings. -->

Rules:
- Omit milestone lines if no milestone is assigned
- Omit interface layers line if `## Interface Layers` absent from project_summary.md and no knowledge file loaded
- Siblings come from `_ISSUE_LANDSCAPE` filtered by same `milestone_number`

### 6d — AC format

**AC bullets: verb-object, ≤10 words each. No prose.**
- ✓ `"Submit creates a GitHub issue with correct labels"`
- ✗ `"When the user clicks the submit button, a new issue should appear..."`

### 6e — agent_workflow

Generate based on size:

- **trivial** → omit `agent_workflow` field entirely
- **small** → orientation step only + 1–2 specific steps:
  - Step 1: `"Skim the relevant file(s) for this change, check for existing patterns, make the fix."`
  - Step 2–3: specific to this issue
- **medium/large** → orientation step + issue-specific steps:
  - Step 1: `"Orient yourself as an experienced developer picking up this task. If dispatch_task is available: call dispatch_task('structure_scan', file_tree_content) to get an area map, and call dispatch_task('file_location', issue_title + body) to get relevant files — use results to inform your concrete plan. Otherwise: if project docs exist (project_summary.md, project_detail.md), scan their headings — read only sections relevant to this area; if no docs, list files and filter by relevance. Stop once you have enough context. State your concrete plan: what you'll change, where, in what order, and what to watch for."`
  - Steps 2–N: specific to this issue (derived from body, AC, feature section)
  - Final step: `"Verify full test suite passes and all AC are met"`

**Do NOT prescribe which files to read. Do NOT use generic steps. Every step after Step 1 must be specific to this issue.**

### 6f — Labels + milestone

**Auto-assign labels** — label cache is already warm from Step 1 — use cached label names (do NOT call `list_repo_labels()` again). Check `label_auto_assign` preference (default `true`):
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

**Auto-assign milestone** — check `milestone_auto_assign` preference (default `true`):
- If `true`/unset (stop at first match):
  1. Title/body references a version or sprint string → assign matching milestone from `_MILESTONE_CACHE`
  2. Exactly one active milestone in `_MILESTONE_CACHE` → assign silently
  3. Multiple active milestones → use `dispatch_task("issue_classification", issue_title + body)` if available to determine likely milestone from size + area; show: `[feat] Add OAuth refresh → M1 Core Auth [auto]` and let user override in edit phase
  4. Multiple milestones, no dispatch_task → ask: "Which milestone? ({names}) / skip"
  5. No milestones → leave unassigned
- Never auto-create a milestone for a single issue.
- **Do NOT auto-assign milestone when:** issue is a question/discussion/support request, labelled `wontfix`/`duplicate`/`invalid`, or is a tracking/epic issue spanning multiple deliverables.

### 6g — Draft, confirm, submit

3. Call `draft_issue(title, body, labels, assignees, agent_workflow=[...], milestone_number=N_or_None)` for each — **silent**
4. Show confirmation block:
   ```
   About to: Create {N} GitHub issues on {repo}
     {issue-1-title} [{size}] [{labels}]
     {issue-2-title} [{size}] [{labels}]
     ...
   Proceed? (yes / review first / cancel)
   ```
   Wait for explicit "yes".
5. Call `submit_issue(slug)` for each — **silent**

### 6h — Doc updates (medium/large only)

Skip all doc updates for **trivial** and **small** issues.

For **medium/large**, check `confirm_arch_changes` preference first:
- `true` or unset → show one-line preview, ask "Update project notes? (yes/no)"
- `false` → update silently

| Labels | Action |
|--------|--------|
| `enhancement` or `feature` | (a) `update_project_detail_section(feature_name, content)` — include `**Milestone:** Mx` at top. (b) `update_project_summary_section(section_name="Planned Features", content=...)` — merge rows, never replace. |
| `architecture` | `update_project_summary_section(section_name="Design Principles", content=...)` |
| `bug`, `chore`, `refactor`, `docs` only | No update. |
| No labels | Ask: "Should I add this to the design notes? (yes/no)" |

**Planned Features row format:**
```
| #{N} | {title} | M2 — Posting | feature, backend | api, backend |
```
6. **Offer implementation** — ask immediately after issues are submitted:
   > "Implement now using /th:gh-implementation? (yes / no)"
   - **yes** → call `apply_unload_policy(command="gh-plan")` — output `_display` as a standalone line,
     then invoke `/th:gh-implementation` — this switches mode automatically.
     Do NOT ask about cache cleanup separately; the unload happens as part of the switch.
   - **no** → ask: "Unload cached data to keep context lean? (yes/no)"
     - If yes: call `apply_unload_policy(command="gh-plan")` — output `_display` as a standalone line.
     - If no: proceed.
7. Say: **"Issues drafted and submitted! Let me know if you'd like me to start implementing or if you want to change any issues!"**

---

## Sub-commands available independently

| Command | Say | Does |
|---------|-----|------|
| `/th:gh-plan-list` | "list issues" | Show issue table |
| `/th:gh-plan-create` | "create an issue" | Single guided issue |
| `/th:gh-plan-analyze` | "analyze my repo" | Build project docs |
| `/th:gh-plan-setup` | "set up github" | Workspace init |
| `/th:gh-plan-auth` | "fix auth" | Auth recovery |
