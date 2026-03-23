# /th:current-stat — Show active workspace state

Quick status snapshot for the current terminal-hub session.

## What it does

1. Call `get_runtime_state`
2. Read `result._display` and print it as-is — do not add prose, do not narrate
3. If `result.status == "needs_init"`: say "Workspace not initialised. Run `/th:gh-plan-setup` to get started."

## Output format

Print the `_display` value verbatim inside a code block so alignment is preserved:

```
terminal-hub active state
──────────────────────────────────────────────────
RUNTIME
  • github_planner — GitHub issue planning — analyze repos, plan work, create and track issues. (N tools)
  N tools total — full function awareness active
──────────────────────────────────────────────────
CACHES
[cache ] Analyzer snapshot         ✓  2.3h old
[prompt] Project summary           ✓  1024 bytes
[prompt] Project detail            ✗
[cache ] Tracked issues            ✓  3 total · 2 pending · 1 open
──────────────────────────────────────────────────
GitHub repo: owner/repo  (mode: github)
Runtime reflects server startup state.
```

## Rules

- Call `get_runtime_state` once — do not call any other tool
- Print only the `_display` block — no extra commentary unless the user asks
- If the user follows up with "why is X missing?" — answer conversationally using the `items` array from the result
