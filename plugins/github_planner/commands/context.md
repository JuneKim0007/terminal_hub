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
3. Call `update_project_description(content=...)`
4. Confirm: > "Saved to hub_agents/project_description.md"

## Save architecture notes

1. Call `get_project_context(file="architecture")` first
2. Merge user input with existing
3. Call `update_architecture(content=...)`
4. Confirm: > "Saved to hub_agents/architecture_design.md"

## Rules

- Always read before writing — never blindly overwrite existing content
- Keep descriptions in markdown; include headings for easy future scanning
