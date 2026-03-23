# Quick Start

Go from zero to planning and implementing your first GitHub issue in 5 minutes.

---

## Prerequisites

```bash
pip install terminal-hub
terminal-hub install
# restart Claude Code
```

See [installation.md](installation.md) for full setup including GitHub auth.

---

## Step 1 — Start the planner

Open Claude Code in your project directory and say:

> "let's plan"

or type `/th:gh-plan` directly. terminal-hub will:
- Check your workspace (set up `hub_agents/` if first time)
- Ask which GitHub repo to connect (or use local-only mode)
- Analyze your codebase if no project docs exist yet

---

## Step 2 — Describe a feature

Tell Claude what you want to build in plain English:

> "I want to add a login endpoint that accepts email and password and returns a JWT"

terminal-hub expands this into a structured GitHub issue:
- Title, body, acceptance criteria
- Labels (`feature`, `auth`, etc.)
- An agent workflow — step-by-step instructions for how Claude should implement it

You'll see a preview before anything is submitted.

---

## Step 3 — Approve and submit

```
Draft ready:
  Title: feat: add POST /auth/login endpoint with JWT response
  Labels: feature, auth
  Workflow: 6 steps

Submit to GitHub? (yes / edit / skip)
```

Say **yes** — the issue is created on GitHub and saved locally in `hub_agents/issues/`.

---

## Step 4 — Implement it

Say:

> "implement this issue"

or `/th:gh-implementation`. Claude will:
1. Load the issue context and agent workflow
2. Implement the changes
3. Show you the diff

```
Changes ready — 3 files modified.
Accept? (yes / review more / cancel)
```

Say **yes** — Claude commits, pushes, and closes the issue.

---

## Step 5 — Write docs (optional)

After all issues are closed, terminal-hub prompts:

> "All issues are closed. Want me to write or update docs? (/th:gh-docs)"

Say **yes** — it generates or updates `README.md` and `CONTRIBUTING.md`, then asks whether to open a PR or push directly.

---

## That's it

The full loop: plan → implement → document, driven by natural conversation. No manual orchestration needed.

For the full command reference, see [commands.md](commands.md).
