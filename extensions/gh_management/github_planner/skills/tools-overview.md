---
name: tools-overview
description: Quick-reference index of all gh_management MCP tools — name, purpose, when to call. Always loaded.
alwaysApply: true
triggers: []
---

# gh_management Tools Overview

| Tool | Purpose | Call when |
|------|---------|-----------|
| `set_project_root` | Set active project root so hub_agents/ writes to the user's project | First call in every /th: command |
| `confirm_session_repo` | Check whether the current session repo has been confirmed | Step 1 of gh-plan and gh-implementation |
| `set_session_repo` | Lock a confirmed repo for the session | After user confirms repo or specifies a change |
| `check_auth` | Check GitHub authentication status | On any GitHub auth error |
| `verify_auth` | Verify auth after user runs `gh auth login` | After user reports completing auth |
| `draft_issue` | Save an issue draft locally as status=pending | Before submitting; show user a preview first |
| `generate_issue_workflows` | Append agent + program workflow scaffolding to an existing issue | After draft_issue when no workflow exists |
| `submit_issue` | Submit a pending local draft to GitHub | After user approves the draft |
| `list_issues` | Return tracked issues from local hub_agents/issues/ files | At session start; before issue selection |
| `sync_github_issues` | Fetch GitHub issues and cache them locally | When local cache is stale or missing |
| `list_pending_drafts` | Return only locally-created, never-submitted issues | To check for status drift |
| `get_issue_context` | Read a specific issue file by slug | To reload a specific issue's context cheaply |
| `load_active_issue` | Load an issue into session context (sets active issue state) | Step 4 of gh-implementation |
| `unload_active_issue` | Clear active issue session state and optionally delete local file | Step 10 of gh-implementation (mandatory) |
| `close_github_issue` | Close a GitHub issue | Step 8 of gh-implementation after push |
| `update_project_detail_section` | Merge a single H2 section into project_detail.md | After feature/enhancement shipped |
| `update_project_summary_section` | Merge a single H2 section into project_summary.md | After milestone creation, design changes |
| `update_project_description` | Overwrite hub_agents/project_description.md | During new-repo setup |
| `update_architecture` | Overwrite hub_agents/architecture_design.md | When architecture changes |
| `save_project_docs` | Initialise project_summary.md with structured fields | During repo setup or first analysis |
| `load_project_docs` | Read project docs from cache or disk | Step 2 of gh-implementation; Step 4 of gh-plan |
| `docs_exist` | Check whether project_summary.md and project_detail.md exist | Before analysis step |
| `lookup_feature_section` | Return the project_detail.md section matching a feature name | Before drafting medium/large issues |
| `get_session_header` | Return a ≤80-token context blob for session start | At session start to decide doc loading |
| `get_file_tree` | Return an organized file-tree index of the workspace root | When structure scan is needed |
| `set_preference` | Persist a user preference in hub_agents/config.yaml | When user expresses a persistent preference |
| `format_prompt` | Format a yes/no or choice prompt for display | Before every user prompt |
| `analyze_repo_full` | Fetch the full repo tree and return a compact file index | During repo analysis (gh-plan-analyze) |
| `start_repo_analysis` | Fetch the full file tree and queue files for analysis | Start of incremental analysis flow |
| `fetch_analysis_batch` | Fetch the next batch of files from the analysis queue | During incremental analysis loop |
| `get_analysis_status` | Return current analysis progress from runtime cache | During incremental analysis loop |
| `run_analyzer` | Analyze the GitHub repo and write a snapshot | When a full analyzer snapshot is needed |
| `list_repo_labels` | Fetch and cache all labels from the GitHub repo | Step 1 warm-up; before drafting issues |
| `analyze_github_labels` | Fetch and classify GitHub labels as active/closed | When label health check is needed |
| `load_github_local_config` | Read saved github_local_config.json | When repo-specific config is needed |
| `load_github_global_config` | Read or create hub_agents/github_global_config.json | For auth method and default repo info |
| `save_github_local_config` | Merge data into github_local_config.json | When saving repo-specific fields |
| `get_github_config` | Return GitHub config for global/local/both scope | When GitHub config is needed |
| `get_setup_status` | Return workspace initialisation status | Step 1 of gh-plan |
| `setup_workspace` | Initialise hub_agents/ directory structure | During workspace setup |
| `list_milestones` | List GitHub milestones (uses in-memory cache) | Step 1 warm-up; before milestone assignment |
| `create_milestone` | Create a GitHub milestone (idempotent) | Step 2.5 of gh-plan after user approves |
| `assign_milestone` | Assign a milestone to a local issue | After issue creation or reclassification |
| `generate_milestone_knowledge` | Generate a structured knowledge file for a milestone | After milestone creation |
| `load_milestone_knowledge` | Load the knowledge file for a milestone | Step 6b of gh-plan for medium/large issues |
| `create_github_repo` | Create a new GitHub repo under the authenticated user | During new-repo path (gh-plan Step 2b) |
| `make_label` | Create a GitHub label (idempotent) | Before drafting issues when label is missing |
| `get_scan_profile_status` | Check if hub_agents/scan_profile.yaml exists | Start of gh-plan-analyze |
| `create_scan_profile` | Create hub_agents/scan_profile.yaml | When user confirms scan profile creation |
| `get_project_context` | Read project_description.md and/or architecture_design.md | Before updating project description |
| `save_docs_strategy` | Persist how to handle existing .md docs found during analysis | During repo analysis step (b) |
| `load_docs_strategy` | Load the saved existing-docs strategy | Before generating TH docs |
| `search_project_docs` | Search project for useful .md docs to connect as references | During connected-docs setup |
| `connect_docs` | Connect existing project docs as references | When user has existing docs to link |
| `load_connected_docs` | Load the primary connected reference doc or a specific section | When primary ref doc is connected |
| `load_skill` | Load a skill file from the registry by name | When a skill is needed on demand |
| `apply_unload_policy` | Apply the unload policy for a command | On command exit or mode switch |
| `unload_plugin` | Clear all in-memory caches for a plugin | Full cache reset |
| `list_plugin_state` | Inventory all resources loaded by a plugin | Before unload_plugin |
| `dispatch_task` | Dispatch a sub-task to a lightweight model (Haiku) | File-location / scan / classification tasks |
| `announce_command_load` | Announce that a command has been loaded | At start of command execution |
