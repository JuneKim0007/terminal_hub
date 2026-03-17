# Workflow: Auth recovery

**Trigger:** Any GitHub tool returns `{error: "github_unavailable"}` or `{authenticated: false}`

## Steps

1. Call `check_auth()`

2. If `authenticated: true` — auth is fine, the original error was likely a repo config issue.
   Ask the user to confirm their repo with `setup_workspace(github_repo="owner/repo")`.

3. If `authenticated: false`, present the options from the response:
   > "GitHub authentication isn't set up. You can:"
   > "  a) Run `gh auth login` in your terminal (recommended)"
   > "  b) Set `GITHUB_TOKEN=<token>` in your environment"

4. After the user reports they've run `gh auth login`:
   - Call `verify_auth()`
   - If `authenticated: true`: > "Authenticated. Retrying your original request..."
     Then retry the tool call that originally failed.
   - If still false: repeat step 3.

## Rules

- Never ask the user to paste a token into the chat
- After successful `verify_auth`, always retry the originally-failed tool automatically
