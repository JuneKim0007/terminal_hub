# Workflow: Create and track issues

**Trigger:** User mentions a task, bug, feature request, or asks what to work on next.

## Create an issue

1. Gather from the user (ask only what's missing):
   - **title** — short, imperative (e.g. "Fix login redirect")
   - **body** — context, reproduction steps, or acceptance criteria
   - **labels** — optional (e.g. `["bug", "priority-high"]`)
   - **assignees** — optional GitHub usernames

2. Call `docs_exist()` to check for project context:
   - If `summary_exists: false` → skip doc lookup, proceed with user-provided info
   - If `summary_exists: true` and sections list is non-empty:
     - Infer the relevant feature area from the issue title
     - Call `lookup_feature_section(feature="...")` to get design constraints
     - If `matched: true`: use `section` to inform AC and `global_rules` for constraints
     - If `matched: false`: note the available sections but don't block creation

3. Call `draft_issue(title=..., body=..., labels=..., assignees=...)` to save locally.

4. Optionally call `generate_issue_workflows(slug=...)` to append agent + program
   workflow scaffolding to the issue file (recommended for implementation tasks).

5. If the user wants to publish to GitHub, call `submit_issue(slug=...)`.

6. On success, confirm:
   > "Created issue #`{issue_number}`: `{url}`
   > Saved locally at `{local_file}`."

7. On `{error: "github_unavailable"}` → follow `terminal-hub://workflow/auth`.

## List issues

1. Call `list_issues()`
2. Present as a numbered list: `#{issue_number} — {title} ({slug})`
3. Offer: "Would you like context on any of these?"

## Reload issue context

1. Use the slug from `list_issues` output
2. Call `get_issue_context(slug="...")`
3. Summarise the issue body and front matter for the user

## Rules

- Never guess a slug — always get it from `list_issues` first
- If `local_file` is null in the create response, warn the user the local write failed but the GitHub issue was created successfully
