# Workflow: Project context

**Trigger:** Session start (after init), or user describes the project / architecture.

## Load context at session start

1. Call `get_project_context(file="all")`
2. If both fields are non-null, summarise briefly for the user:
   > "Loaded saved context: {project_description summary} / {architecture summary}"
3. If null, offer to capture it:
   > "No project context saved yet. Want me to record a description or architecture notes?"

## Save project description

1. Call `get_project_context(file="project_description")` first to avoid overwriting
2. Merge user input with any existing content
3. Show the proposed new content to the user and ask (#85):
   > "I'll save this as your project description. Confirm? (yes / edit / cancel)"
4. Wait for explicit "yes" before calling `update_project_description(content=...)`
5. Confirm: > "Saved to hub_agents/project_description.md"

## Save architecture notes

1. Call `get_project_context(file="architecture")` first
2. Merge user input with existing
3. Show the proposed new content and ask (#85):
   > "I'll save this as your architecture notes. Confirm? (yes / edit / cancel)"
4. Wait for explicit "yes" before calling `update_architecture(content=...)`
5. Confirm: > "Saved to hub_agents/architecture_design.md"

## Update a single feature section

1. Infer the feature area from context
2. Show proposed section content and ask:
   > "I'll add/update the '{feature_name}' section in project_detail.md. Confirm? (yes / edit / cancel)"
3. Wait for "yes", then call `update_project_detail_section(feature_name, content)`

## Rules

- Always read before writing — never blindly overwrite existing content
- Always show proposed content and wait for user confirmation before any write (#85)
- Keep descriptions in markdown; include headings for easy future scanning
