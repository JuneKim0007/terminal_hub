# /t-h:github-planner/unload

Unload the gh_planner plugin — clears all in-memory caches and volatile disk files.

## Steps

1. Call `list_plugin_state(plugin="gh_planner")`
   - Show the user what will be cleared (caches and disk files)
   - If nothing is loaded: respond "Nothing to unload — plugin state is already clean."

2. Call `unload_plugin(plugin="gh_planner")`

3. Check the result:
   - `success: true` → respond: **"Unloading successful!"**
   - `success: false` → analyze each item in `errors[]`:
     - For permission errors: ask the user to check file permissions
     - For missing directory errors: treat as already clean (non-fatal)
     - For other errors: report clearly and suggest restarting the MCP server
   - Retry non-fatal errors once if possible, then report remaining failures

## What is cleared

- In-memory: `_ANALYSIS_CACHE`, `_PROJECT_DOCS_CACHE`, `_FILE_TREE_CACHE`, `_SESSION_HEADER_CACHE`
- Disk: `analyzer_snapshot.json`, `file_hashes.json`, `file_tree.json`

## What is NOT cleared

- `hub_agents/issues/` — your tracked issues are preserved
- `project_summary.md`, `project_detail.md` — your project docs are preserved
