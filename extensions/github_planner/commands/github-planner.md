# /t-h:github-planner — Integrated planning flow

<!-- RULE: after any draft_issue or submit_issue call, do not narrate the result.
     Continue the planning conversation. When all planned issues are created, say:
     "Let me know any plans for this!" -->

You are in **github-planner** mode — the integrated flow that orchestrates
analysis, planning, and issue creation through natural conversation.
Sub-commands handle each step; this command composes them.

---

## Step 1 — Workspace + auth check

Call `get_setup_status`.
- `initialised: false` → run the **setup sub-command** workflow (`/t-h:github-planner/setup`)
- `initialised: true` → continue

---

## Step 2 — Repo identification

Ask:
> What repo are we planning for?
> a) GitHub URL or `owner/repo`  b) Use configured repo  c) Brand-new repo

- **(b)**: read env, skip to Step 3
- **(c)**: ask name/language/description → skip analysis → Step 5 (no doc lookup)
- **(a)**: call `setup_workspace(github_repo=...)` if not already set

---

## Step 3 — Project docs check

Call `get_session_header` (if available) or `docs_exist`.
- Docs < 7 days old → "I have project notes from {N}h ago. Use them, or re-analyze?"
- Docs ≥ 7 days or missing → recommend the **analyze sub-command** workflow

If re-using existing docs → skip to Step 5.
If analyzing → run the **analyze sub-command** workflow (`/t-h:github-planner/analyze`).

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
2. Call `draft_issue(title, body, labels, assignees)` for each — **silent**
3. Show count: "Drafted {N} issues. Push to GitHub? (yes / review first)"
4. If yes: call `submit_issue(slug)` for each — **silent**
5. **Auto-update project docs** (only for new features, not bug fixes or refactors):
   - If any drafted issue introduces a new feature area not in `docs_exist.sections`:
     call `load_project_docs(doc="detail")`, append a new H2 section for that area
     with what was planned (future-tense guidelines), then call `save_project_docs`.
   - If an existing section was extended: call `lookup_feature_section`, merge the
     planned work into Extension Guidelines, save updated docs.
   - Bug fix / refactor issues → **do not update project docs**.
6. Say: **"Let me know any plans for this!"**

---

## Sub-commands available independently

| Command | Say | Does |
|---------|-----|------|
| `/t-h:github-planner/list-issues` | "list issues" | Show issue table |
| `/t-h:github-planner/create-issue` | "create an issue" | Single guided issue |
| `/t-h:github-planner/analyze` | "analyze my repo" | Build project docs |
| `/t-h:github-planner/setup` | "set up github" | Workspace init |
| `/t-h:github-planner/auth` | "fix auth" | Auth recovery |
