# Workflow: Create and track issues

**Trigger:** User mentions a task, bug, feature request, or asks what to work on next.

For the full guided flow use `/t-h:github-planner/create-issue`.

## Quick create (no project docs)

1. Gather: title (imperative), body (what/why/AC), labels, assignees
2. Call `draft_issue(title, body, labels, assignees)` — saves locally as pending
3. Ask: "Push to GitHub? (yes / save locally for now)"
4. If yes: call `submit_issue(slug)`
5. Say: "Let me know any plans for this!"

## Create with project context (preferred when docs exist)

1. Call `docs_exist` — if `summary_exists: false`, use Quick create above
2. Identify the feature area from the user's description
3. Call `lookup_feature_section(feature="<area>")`
   - `matched: true` → use `section` for AC, `global_rules` for Constraints
   - `matched: false` → proceed without feature AC
4. Draft body with structure:
   ```
   ## What / ## Why / ## Acceptance Criteria / ## Constraints
   ```
5. Show preview → `draft_issue` → optionally `submit_issue`

## List issues

1. Call `list_issues(compact=true)` — returns `{slug, title, status}` only (~3× fewer tokens)
2. Present as numbered list: `#{issue_number} — {title} ({status})`
3. Offer: "Want context on any of these?"

## Reload issue context

1. Get slug from `list_issues`
2. Call `get_issue_context(slug="...")`
3. Summarise issue body and front matter

## Rules

- Never guess a slug — always get it from `list_issues` first
- Never re-submit an already-open issue — `submit_issue` will return `error: already_submitted`
- Use `compact=true` in `list_issues` unless the user needs full details
