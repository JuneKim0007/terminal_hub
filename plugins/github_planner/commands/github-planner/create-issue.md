# /t-h:github-planner/create-issue

<!-- RULE: after draft_issue or submit_issue, do not narrate the result.
     Continue conversation or say: "Let me know any plans for this!" -->

Guided single-issue workflow:

1. If workspace not initialised, call `get_setup_status` and handle setup first.
2. Ask: "What's the issue? Describe the bug, feature, or task."
3. Listen. Ask one clarifying question if scope is unclear.
4. Propose: title (one line) + body (structured: what/why/acceptance criteria).
5. Show preview. Ask: "Create this? (yes / edit)"
6. On yes: call `draft_issue(title, body, labels, assignees)`.
7. Ask: "Push to GitHub now? (yes / save locally for now)"
8. If yes: call `submit_issue(slug)`.
9. Say: "Let me know any plans for this!"
