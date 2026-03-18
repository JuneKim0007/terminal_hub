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

Ask:
> What repo are we planning for?
> a) GitHub URL or `owner/repo`  b) Use configured repo  c) Brand-new repo

- **(b)**: read env, skip to Step 3
- **(c)**: brand-new repo → follow **New-repo path** below
- **(a)**: call `setup_workspace(github_repo=...)` if not already set

### New-repo path (#83)

When the user selects (c) or `get_session_header` returns `{docs: false}` and GitHub history is empty:

1. Engage conversationally: "Tell me about your project — what is it, what's the main tech stack, and what are you building first?"
2. From conversation: draft a minimal `project_summary.md` stub (no code analysis needed).
   Show it: "I'll save this as your project description. Confirm? (yes / edit / cancel)"
3. On confirm: call `update_project_description(content=...)`.
4. Ask: "Want me to break your first features into issues? (yes / describe features first)"
5. On yes: continue to Step 5 (planning conversation) — skip analysis entirely.
6. Issue creation uses standard Step 6 flow with confirmation hook (#82).

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
2. Call `draft_issue(title, body, labels, assignees)` for each — **silent**
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

   | Labels on the batch | Action |
   |---------------------|--------|
   | Any issue has `enhancement` or `feature` | Call `update_project_detail_section(feature_name, content)` to merge a new or updated section. Do **not** rewrite the full file. |
   | Any issue has `architecture` | Update `project_summary.md` Design Principles section via `update_project_detail_section`. |
   | All labels are `bug`, `chore`, `refactor`, or `docs` | **No doc update** — zero extra API calls. |
   | No labels set | Ask user: "This looks like a new feature — should I add it to the design dictionary? (yes/no)" — then follow appropriate row above. |

   `update_project_detail_section(feature_name, content)` merges a single H2 section
   into `project_detail.md` without rewriting the rest of the file.
6. Say: **"Let me know any plans for this!"**

---

## Sub-commands available independently

| Command | Say | Does |
|---------|-----|------|
| `/th:github-planner/list-issues` | "list issues" | Show issue table |
| `/th:github-planner/create-issue` | "create an issue" | Single guided issue |
| `/th:github-planner/analyze` | "analyze my repo" | Build project docs |
| `/th:github-planner/setup` | "set up github" | Workspace init |
| `/th:github-planner/auth` | "fix auth" | Auth recovery |
