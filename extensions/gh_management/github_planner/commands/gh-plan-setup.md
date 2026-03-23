# Workflow: Initialise workspace

**Trigger:** `get_setup_status` returns `{initialised: false}`

## Steps

1. Ask conversationally:
   > "What are you building? Tell me the idea — what it does, any tech stack preferences, and how big."

2. From the answer, infer a project name and one-line goal. Confirm before proceeding:
   > "Here's what I have — **Name:** <name>, **Goal:** <one-line>. Look right? (yes / tweak)"

3. Ask:
   > "Keep it local, or connect to GitHub too? (local / github)"
   - **local** → call `setup_workspace()` (no argument)
   - **github** → ask "Use an existing repo (`owner/repo`) or create a new one? (existing / new)"
     - **existing** → call `setup_workspace(github_repo="owner/repo")`
     - **new** → call `create_github_repo(name=<name>, description=<goal>, private=true)`,
       then `setup_workspace(github_repo=<owner/repo>)`

4. Confirm success:
   > "Done! terminal-hub is ready. hub_agents/ has been created and gitignored."

5. If `github_repo` was set and auth is uncertain → call `check_auth` immediately.
   If not authenticated → follow `terminal-hub://workflow/auth`.

6. Proceed to `terminal-hub://workflow/context` to reload any saved project context.

## Error cases

| Response | Action |
|----------|--------|
| `setup_workspace` fails with any error | Report the error message verbatim, ask the user to check directory permissions |
