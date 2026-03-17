# /t-h:github-planner/list-issues

<!-- RULE: Show the issue list concisely. Do not narrate tool call details. -->

Call `list_issues(compact=True)` and render the result as a clean table:

| Slug | Title | Status |
|------|-------|--------|

Group by status: pending → open → closed. Show counts at the top.

If no issues: "No issues tracked yet. Say 'create an issue' to start."

After showing the list, say: "Let me know any plans for this!"
