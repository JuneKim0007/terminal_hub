# /terminal_hub:conversation — Plugin Registry & Awareness

<!-- RULE: Call scan_plugins silently. Only show the summary table, not raw JSON. -->

You are in **conversation** mode. Your job is to build and display the plugin registry
so the user understands what terminal-hub can do for them.

## Step 1 — Load or build registry

Call `load_plugin_registry`.

- If `_suggest_scan` is present (registry missing): call `scan_plugins` silently, then re-call `load_plugin_registry`.
- If `unidentified > 0`: say "I found {N} plugin(s) without a usage description — you may want to add `description.json` to those extensions."

## Step 2 — Display registry

Present a compact table:

```
Available plugins ({N} total):

| Plugin              | Entry Command                    | When to use |
|---------------------|----------------------------------|-------------|
| GitHub Planner      | /th:github-planner              | Plan work, create and track GitHub issues |
| Plugin Creator      | /th:create-plugin               | Create a new terminal-hub plugin |
```

## Step 3 — Offer to match

Say:
> "Tell me what you'd like to do and I'll suggest the best plugin, or just invoke one directly."

Then listen. When the user describes a task, use the `triggers` and `usage` fields from the
registry to identify the best plugin and suggest its entry command.

## Rules

- Never dump raw JSON to the user
- If no plugin matches, say what you can help with directly
- If registry is stale (last_scanned > 24h), suggest re-running scan_plugins
