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
- **(c)**: ask name/language/description → skip analysis → Step 5
- **(a)**: call `setup_workspace(github_repo=...)` if not already set

---

## Step 3 — Project docs check

Call `get_session_header` (if available) or `docs_exist`.
- Docs < 7 days old → "I have project notes from {N}h ago. Use them, or re-analyze?"
- Docs ≥ 7 days or missing → recommend the **analyze sub-command** workflow

If re-using existing docs → skip to Step 5.
If analyzing → run the **analyze sub-command** workflow (`/t-h:github-planner/analyze`).

---

## Step 4 — Load project context (silent)

Call `load_project_docs(doc="summary")`. Absorb silently — do not show to user.

---

## Step 5 — Planning conversation

Say: **"Let me know any plans for this!"**

- Use project summary as background context (silent)
- Load `project_detail.md` only when user references a specific file/module
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
1. Call `draft_issue(title, body, labels, assignees)` for each — **silent**
2. Show count: "Drafted {N} issues. Push to GitHub? (yes / review first)"
3. If yes: call `submit_issue(slug)` for each — **silent**
4. Say: **"Let me know any plans for this!"**

---

## Sub-commands available independently

| Command | Say | Does |
|---------|-----|------|
| `/t-h:github-planner/list-issues` | "list issues" | Show issue table |
| `/t-h:github-planner/create-issue` | "create an issue" | Single guided issue |
| `/t-h:github-planner/analyze` | "analyze my repo" | Build project docs |
| `/t-h:github-planner/setup` | "set up github" | Workspace init |
| `/t-h:github-planner/auth` | "fix auth" | Auth recovery |
