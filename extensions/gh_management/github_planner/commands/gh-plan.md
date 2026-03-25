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

**Skill setup (once per session):** If `hub_agents/skills/` does not exist, prompt once:
> "I can load a skills index for this project to guide my behaviour.
> Do you have one? (point me to the path / create a starter for me / skip)"
> - **point me to path** → call `connect_docs(skills="<path>")`
> - **create a starter** → generate `hub_agents/skills/SKILLS.md` and call `connect_docs(skills="hub_agents/skills/SKILLS.md")`
> - **skip** → proceed; only plugin-level skills (Tier 1) will be used

**Persistent skills:** Call `_load_skill_registry` (triggered by `get_session_header` or `set_project_root`) — skills with `alwaysApply: true` (`SKILLS.md`, `tools-overview.md`) are automatically available.
- `initialised: false` → run the **setup sub-command** workflow (`/th:gh-plan-setup`)
- `initialised: true` → continue

**Repo confirmation (#148):** If `github_repo` is set, call `confirm_session_repo()`.
- `confirmed: true` → proceed silently (already confirmed this session — sync + landscape already ran)
- `confirmed: false` → print `_display` verbatim, then ask user "yes / change":
  - "yes" → call `set_session_repo(repo=...)` to lock it, then run **post-lock steps** below
  - "change" → ask "Which repo? (owner/repo)", then call `set_session_repo(repo=new_repo)`, then run **post-lock steps** below

**Post-lock steps (after fresh repo lock only — skip when confirmed: true):**

Call `list_milestones()` silently.
This warms the milestone cache so `assign_milestone` never makes a cold API call.
If the call fails with 404 or auth error, surface it immediately — bad repo config
should be caught here, not at submit time.

**Milestone cache check (#49):** After `list_milestones()` completes, check `milestone_assign` preference via `read_preference("milestone_assign")`. If the preference is not `False` and `list_milestones()` returned 0 milestones, scan local issues (from `list_issues()`) for any that have a `milestone_number` set. If any are found, offer once per session:
> "Some issues have milestone assignments but no milestones exist on GitHub — fetch them? (yes / skip)"
- **yes** → call `list_milestones()` again (forces a fresh fetch); if still empty, note "No milestones found on GitHub — milestone assignments may be stale."
- **skip** → proceed without milestones; do not ask again this session.

**Auto-sync + landscape (runs after cache warming, once per fresh repo lock):**

1. Call `sync_github_issues()` — silent. Print one status line:
   `🔄 Synced — {N} open issues from GitHub` (append `· {M} local drafts pending` if local-only drafts exist)
   If sync fails, surface the error and continue without landscape.

2. Call `list_issues(compact=False)`. If no open issues returned, print:
   `No open issues — let's plan something!` and continue to Step 3.

3. Otherwise, group open issues by `milestone_number` ascending (unassigned/null last).
   Display the landscape using milestone titles from `_MILESTONE_CACHE`:
   ```
   📋 Open issues by milestone:

   M{N} — {milestone title} ({count} open)
     #{number} [{type label}] {title}

   Unassigned ({count} open)
     #{number} [{type label}] {title}
   ```
   `{type label}`: use the first label matching bug/feature/enhancement/refactor/chore/documentation/performance. Omit brackets if none match.

4. Call `format_prompt(question="These are your unimplemented plans. What would you like to do?", options=["implement", "review", "plan more", "skip"], style="question")` — print `_display` verbatim.
   - **implement** → call `apply_unload_policy(command="gh-plan")`, print `_display`, then invoke `/th:gh-implementation`
   - **review** → ask "Which issue? (number or title)" → show that issue's full body from the `list_issues` result
   - **plan more** → continue to Step 3
   - **skip** → continue to Step 3 silently

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

<!-- SKILL: load_skill("milestones") — contains milestone derivation, auto-assignment, sequential planning rules -->

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

**Design principle detection (always active in this step):**
If any user message contains trigger phrases — "always", "never", "every time", "must always", "should always", "don't ever", "every X must", "all X should" — before responding to the main message:
1. Call `format_prompt(question="That sounds like a design principle — add it to your project docs?", options=["yes", "no"], style="confirm")` — print `_display` verbatim
2. If "yes": read `hub_agents/docs_config.json` → find entry with `primary: true` or `type: "design"` → append `- {principle text} *(added {date})*` under `## Design Principles`. Also call `update_project_summary_section(section_name="Design Principles", ...)` to append it there. Confirm: `Saved: "{principle}" → {doc_path}`
3. If no connected design doc found: ask "Which file should I add design principles to? (path / 'create new')". On "create new": create `hub_agents/design_principles.md` with `## Design Principles` heading and call `connect_docs(design="hub_agents/design_principles.md")`
4. If "no": proceed without saving — no friction

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
- **Label suggestions:** labels are loaded lazily — do NOT call `list_repo_labels()` here.
  Suggest from the known type labels: `bug`/`feature`/`enhancement`/`refactor`/`chore`/`documentation`/`performance` + area label if identifiable.
  If the user explicitly asks "what labels are available?", call `list_repo_labels()` and display the names.
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

## Step 5.5 — Context Enrichment (runs before every `draft_issue` call)

Before calling `draft_issue` for any issue, run the enrichment pipeline. Skip only for trivial issues (label: `chore` or `docs`, single-file change).

**Phase 1 — Intent Expansion**
- `load_skill("intent-expansion")` — expand the user's description using domain conventions
- Map to domain (auth / crud / search / upload / ...), apply conventions, filter by stack + design principles
- Produce: `{original, expanded, conventional_patterns, stack_filtered, design_constraints}`

**Phase 2 — Internal Context Scan**
- Call `scan_issue_context(feature_areas=[...])` with the feature areas from Phase 1
- Finds reusable functions/classes, file references, patterns, and pitfalls in `project_detail.md`
- Produce: `{reusable, extend, patterns, pitfalls, sections_scanned}`

**Phase 3 — Knowledge Synthesis**
- Merge `expanded_intent` + `context_findings` into a `knowledge_package`:
  ```
  {what_user_wants, conventional_patterns, reusable, extending, building_new, pitfalls, design_refs, milestone_context}
  ```

**Phase 4 — Write `## Workflow` section**
- `load_skill("workflow")` — use `knowledge_package` to write the body section
- Include: expanded intent, architecture layers, reuse/extend/new breakdown, design decisions, done-when criteria

**Phase 5 — Write `agent_workflow` steps**
- `load_skill("agent-workflow")` — use `knowledge_package` to write each step
- Every step must name explicit file paths, function names, and conventions
- The implementing Claude has zero context — embed everything it needs
- Step format: `"[verb] [what] — [where exactly] — [what to know]"`
- Pass the steps list to `draft_issue(agent_workflow=[...])`

> **Extensibility:** To add a new thinking phase: create a skill file + add to SKILLS.md + reference here. No Python changes needed.

---

## Step 6 — Issue creation

After approval:

<!-- SKILL: load_skill("creating-issues") — contains sizing rules, AC format, agent_workflow generation, label assignment, Planning Context block format -->

### 6g — Draft, confirm, submit

3. **Lazy label load:** Call `list_repo_labels()` now (if not already cached) — this is the only point labels are fetched. Use the returned names to validate label choices before drafting.
   Call `draft_issue(title, body, labels, assignees, agent_workflow=[...], milestone_number=N_or_None)` for each — **silent**
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
   After all submissions complete, label cache is no longer needed — it will be cleared by `apply_unload_policy` below.

### 6h — Doc updates (medium/large only)

<!-- SKILL: load_skill("design-principles") — contains doc update decision table and confirm_arch_changes behavior -->
6. **Offer implementation** — ask immediately after issues are submitted:
   > "Implement now using /th:gh-implementation? (yes / no)"
   - **yes** → call `apply_unload_policy(command="gh-plan")` — output `_display` as a standalone line
     (this clears label cache and other transient state), then invoke `/th:gh-implementation`.
     Do NOT ask about cache cleanup separately; the unload happens as part of the switch.
   - **no** → ask: "Unload cached data to keep context lean? (yes/no)"
     - If yes: call `apply_unload_policy(command="gh-plan")` — output `_display` as a standalone line (clears label cache).
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
