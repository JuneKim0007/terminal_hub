# /th:gh-plan-settings — View and toggle automation preferences

**On load:** call `announce_command_load(command="gh-plan-settings")` and print `_display` verbatim before any other tool call.

## What it does

1. Call `get_runtime_state` or read preferences via `load_github_local_config` to get current preference values
2. Display the full settings table
3. If user asked to change a setting, update it and confirm

## Display format

```
gh-plan automation settings
────────────────────────────────────────────────────────────────
label_auto_assign        true    Auto-infer and assign labels when creating issues
milestone_auto_assign    true    Auto-assign milestone when target is unambiguous
milestone_assign         unset   Propose milestone creation during planning sessions
confirm_arch_changes     true    Ask before updating project_summary / project_detail
────────────────────────────────────────────────────────────────
Say "set label_auto_assign to false" or "turn off auto-milestone" to change.
Changes persist to hub_agents/config.yaml across sessions.
```

## Reading current values

Call `get_runtime_state` and read the `preferences` field. Map each key:

| Preference key | Display name | Default |
|----------------|--------------|---------|
| `label_auto_assign` | label_auto_assign | `true` |
| `milestone_auto_assign` | milestone_auto_assign | `true` |
| `milestone_assign` | milestone_assign | `unset` |
| `confirm_arch_changes` | confirm_arch_changes | `true` |

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

## Rules

- Preferences persist across sessions (stored in `hub_agents/config.yaml`)
- `unset` means the default behaviour applies — same as `true` for all automation prefs
- Setting a preference to its default value is fine; it makes the behaviour explicit
- Never show raw Python `None` — always display `unset`
