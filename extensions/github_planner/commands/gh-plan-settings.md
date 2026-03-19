# /th:gh-plan-settings — View and toggle automation preferences

<!-- LOAD ANNOUNCEMENT: output exactly:
     🟢 Loaded: gh-plan-settings — `extensions/github_planner/commands/gh-plan-settings.md`
     before any tool calls -->

View and change th:gh-plan automation preferences.

## Available preferences

| Key | Default | Description |
|-----|---------|-------------|
| `confirm_arch_changes` | true | Ask before updating project docs |
| `label_auto_assign` | true | Auto-infer and assign labels when creating issues |
| `milestone_auto_assign` | true | Auto-assign milestone when target is unambiguous |
| `milestone_assign` | unset | Whether to propose milestone creation during planning |
| `sequential_milestone_planning` | false | Prompt to plan next milestone after submitting |
| `github_repo_connected` | unset | Whether a GitHub repo is linked |

## Commands

- `show` (default): list all preferences with current values
- `set <key> <value>`: update a preference (true/false/unset)
- `reset`: reset all to defaults

## Steps

1. Call `apply_unload_policy(command="gh-plan-settings")` silently
2. If no args or "show": call `get_runtime_state` and read the `preferences` field; display the full settings table below
3. If "set <key> <value>": call `set_preference(key, value)` — confirm with `✅ **Set:** {key} = {value}`
4. If "reset": call `set_preference` for each key to its default value

## Display format

```
gh-plan automation settings
────────────────────────────────────────────────────────────────
confirm_arch_changes           true    Ask before updating project_summary / project_detail
label_auto_assign              true    Auto-infer and assign labels when creating issues
milestone_auto_assign          true    Auto-assign milestone when target is unambiguous
milestone_assign               unset   Propose milestone creation during planning sessions
sequential_milestone_planning  false   Prompt to plan next milestone after submitting
github_repo_connected          unset   Whether a GitHub repo is linked
────────────────────────────────────────────────────────────────
Say "set label_auto_assign to false" or "turn off auto-milestone" to change.
Changes persist to hub_agents/config.yaml across sessions.
```

Show `unset` (not `None` or `null`) for preferences that haven't been explicitly set.

## Changing a preference

If the user says "set X to Y" / "turn off X" / "disable X" / "enable X":
- Call `set_preference(key, value)` with the correct key and boolean value
- Confirm: "Got it — `{key}` is now `{value}`."

Natural language aliases:
- "turn off auto-label" / "disable label auto-assign" → `label_auto_assign = false`
- "turn off auto-milestone" / "disable milestone auto-assign" → `milestone_auto_assign = false`
- "always confirm doc changes" / "ask before doc updates" → `confirm_arch_changes = true`
- "silent doc updates" / "skip doc confirmations" → `confirm_arch_changes = false`
- "always create milestones" / "enable milestone planning" → `milestone_assign = true`
- "skip milestone planning" → `milestone_assign = false`
- "enable sequential planning" / "plan milestones one by one" → `sequential_milestone_planning = true`
- "disable sequential planning" → `sequential_milestone_planning = false`

## Rules

- Preferences persist across sessions (stored in `hub_agents/config.yaml`)
- `unset` means the default behaviour applies — same as `true` for all automation prefs
- Setting a preference to its default value is fine; it makes the behaviour explicit
- Never show raw Python `None` — always display `unset`
