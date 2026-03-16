# Workflow: Initialise workspace

**Trigger:** `get_setup_status` returns `{initialised: false}`

## Steps

1. Ask the user:
   > "This project hasn't been set up with terminal-hub yet. Would you like GitHub integration?
   > If yes, what is your repository? (format: `owner/repo`)"

2. Based on the answer:
   - **GitHub integration** → call `setup_workspace(github_repo="owner/repo")`
   - **Local only** → call `setup_workspace()` (no argument)

3. Confirm success:
   > "Done! terminal-hub is ready. hub_agents/ has been created and gitignored."

4. If `github_repo` was set and auth is uncertain → call `check_auth` immediately.
   If not authenticated → follow `terminal-hub://workflow/auth`.

5. Proceed to `terminal-hub://workflow/context` to reload any saved project context.

## Error cases

| Response | Action |
|----------|--------|
| `setup_workspace` fails with any error | Report the error message verbatim, ask the user to check directory permissions |
