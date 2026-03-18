# /th:github-planner/unload

Unload the gh_planner plugin — clears caches according to `unload_policy.json`.

## Steps

1. Call `list_plugin_state(plugin="gh_planner")`
   - Show the user what will be cleared
   - If nothing is loaded: respond "Nothing to unload — plugin state is already clean."

2. Call `apply_unload_policy(command="github-planner/unload")`
   - This reads `unload_policy.json` and clears everything in the `unload[]` array
   - Items in `keep[]` (github_repo, workspace_config, preferences) are left intact

3. Check the result:
   - `success: true` → print `_display` verbatim
   - `success: false` → report each item in `errors[]`, suggest restarting MCP server for persistent failures

## What is cleared (per policy)

See `unload_policy.json` → `commands["github-planner/unload"].unload[]`

- In-memory: analysis_cache, project_docs_cache, file_tree_cache, session_header_cache, label_cache, repo_cache
- Disk: analyzer_snapshot.json, file_hashes.json, file_tree.json, github_local_config.json, docs_strategy.json

## What is kept

- `github_repo` — your configured repo stays linked
- `workspace_config` — config.yaml (mode, preferences) preserved
- `hub_agents/issues/` — tracked issues always preserved
- `project_summary.md`, `project_detail.md` — project docs always preserved
