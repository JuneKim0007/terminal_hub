# /th:gh-implementation/session-knowledge — View or change session flags

## What it does

1. Call `get_implementation_session`
2. Display current flags in a readable table
3. If user asked to change a flag, update it and confirm

## Display format

```
Implementation session flags
────────────────────────────────────────
close_automatically_on_gh   true    Push, close branch, and close GitHub issue automatically after user accepts changes
delete_local_issue_on_gh    true    Delete hub_agents/issues/<slug>.md after GitHub issue is closed
────────────────────────────────────────
Say "change X to false" or "turn off auto-close" to update.
```

## Changing flags

If the user says "change X" / "turn off Y" / "set close_automatically_on_gh to false":
- Update the session flag via `set_implementation_session_flag(key, value)` (TODO #128)
- Confirm: "Got it — I won't auto-close issues this session."

## Rules

- Flags are session-scoped — they reset when the session ends unless the user explicitly asks to persist
- "Never ask again" answers set the corresponding flag persistently in hub_agents/config.yaml preferences
- Always display current state before asking for changes
