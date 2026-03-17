# terminal-hub: Inspect Session State

## Your job

Call `get_session_state`. Display the `_display` field verbatim.

Then self-report which terminal-hub slash commands you have already loaded
this session (e.g. "I loaded /github_planner:create earlier this session").
If none, say "No terminal-hub slash commands loaded this session."

## Expand flow

For each item where `status == "present"`, ask in sequence:

  "Expand [label]? (yes / no)"

On yes:
  - analyzer_snapshot → call `get_project_context` or show summarize_for_prompt output
  - project_description → call `get_project_context(doc_key="project_description")`
  - architecture → call `get_project_context(doc_key="architecture")`
  - issues → call `list_issues` and display the full table

On no: skip to next item.

## After all items

Say: "Inspect complete. Run /github_planner:analyze to refresh the snapshot,
or /github_planner:create to draft a new issue."
