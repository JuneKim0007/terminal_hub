# github_planner: Start

You are running the github_planner plugin for terminal-hub.
This is your active workflow — stay in the planner loop until the user says "done", "exit", or "stop".

## Session start sequence

### 1. Check workspace setup
Call `get_setup_status`.
- If `initialised: false` → say "This project hasn't been set up yet." then call `setup_workspace` to initialise inline.
- If `initialised: true` → continue.
- If `plugin_warnings` is non-empty → show them: "⚠ Plugin warnings: [warnings]"

### 2. Check auth (GitHub mode only)
If mode == "github":
  Call `check_auth`.
  - If not authenticated → walk the user through `gh auth login`, then call `verify_auth`.
  - If authenticated → continue.

### 3. Show session state
Call `get_session_state`. Display the `_display` field verbatim.

### 4. Present the planner menu

```
What would you like to do?
  1. Draft a new issue
  2. Push a pending draft to GitHub
  3. List tracked issues
  4. Run repo analyzer
  5. Inspect session state (expand details)
  6. Update project description
  7. Update architecture notes
  8. Exit
```

### 5. Handle each choice

| Choice | Action |
|--------|--------|
| 1 | Ask for title and description, then call `draft_issue`. Show preview and ask "Push to GitHub now? (yes / no)". If yes, call `submit_issue`. |
| 2 | Call `list_issues`. Show pending ones. Ask "Which slug to push?". Call `submit_issue(slug=...)`. |
| 3 | Call `list_issues`. Display all issues in a table: [#][status][title][labels]. |
| 4 | Call `run_analyzer`. Display `_display`. |
| 5 | Call `get_session_state`. Display `_display`. Offer to expand each present item. |
| 6 | Ask for content, then call `update_project_description`. |
| 7 | Ask for content, then call `update_architecture`. |
| 8 | Say "Exiting github_planner. Type /github_planner:start to resume." and stop. |

### 6. After each action

Return to the menu (show only the numbered list, not the full status table).
Ask: "What would you like to do next? (1–8)"

## Loop termination

Stop the loop when:
- User chooses 8
- User says "done", "exit", "stop", or "quit" at any point
- User says "cancel" during a sub-action (return to menu, don't exit)

## Analyzer hint

If `hub_agents/analyzer_snapshot.json` exists when drafting an issue (choice 1),
mention: "Based on your repo patterns, suggested labels: [suggested_labels].
Suggested assignees: [suggested_assignees]."
Use `get_session_state` to check if snapshot is present.
