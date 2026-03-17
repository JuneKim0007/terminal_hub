# Workflow: Project context

**Trigger:** Session start (after init), user describes the project, or user asks about design.

## Load context at session start

1. Call `get_session_header`
   - `docs: false` → offer to analyze: "No project context yet. Run `/t-h:github-planner/analyze` to build it?"
   - `docs: true` → note `title` and `sections` list silently; proceed
   - `docs: true, stale: true` → suggest re-analysis: "Project notes are {N}h old — re-analyze?"

2. Load summary only when planning context is needed:
   - Bug fix / issue creation → use `sections` from session header as routing; call `lookup_feature_section` per area
   - Feature planning / architecture question → call `load_project_docs(doc="summary")`

## Look up a specific feature area

1. Call `lookup_feature_section(feature="<area name>")`
2. If `matched: true`: use `section` (Existing Design + Extension Guidelines) in your response
3. If `matched: false`: show `available_features`; offer to add a new section

## Save project docs (after analysis or conversation)

Use `/t-h:github-planner/analyze` to regenerate docs from code.
For manual updates: call `save_project_docs(summary_md=..., detail_md=...)`.
Always call `load_project_docs(doc="all")` first to avoid overwriting existing content.

## Rules

- Never load `project_detail.md` in full — always use `lookup_feature_section` with a feature name
- `global_rules` returned by `lookup_feature_section` contains the full project_summary.md — no need for a separate `load_project_docs(doc="summary")` call if a section was matched
- After saving docs, `_SESSION_HEADER_CACHE` is cleared automatically — next `get_session_header` call reflects fresh content
