# terminal-hub: Active State

## Your job

Call `get_runtime_state`. Display the `_display` field verbatim.

Then self-report which terminal-hub slash commands you have already loaded
this session (e.g. "I loaded /github_planner:create earlier this session").
If none, say "No terminal-hub slash commands loaded this session."

## Expand flow

For each cache item where `status == "present"`, ask in sequence:

  "Expand [label]? (yes / no)"

On yes:
  - analyzer_snapshot → call `get_project_context` or show summarize_for_prompt output
  - project_summary → call `get_project_context(doc_key="project_description")`
  - project_detail → call `get_project_context(doc_key="architecture")`
  - issues → call `list_issues` and display the full table

On no: skip to next item.

## Load warnings

If `runtime.load_warnings` is non-empty, highlight each warning with ⚠ and suggest
the user check their plugin manifests.

## After all items

Say: "Active state complete. Run /github_planner:analyze to refresh the snapshot,
or /github_planner:create to draft a new issue."
