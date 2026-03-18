# /th:converse — Plugin Directory & Intent Matcher

<!-- RULE: Never dump raw JSON. Display only plugin name + 1-2 line description. -->

You are in **converse** mode. Show available plugins and match user intent to the right one.

---

## Step 1 — Load registry (smart, no redundant scanning)

Call `load_plugin_registry`.

**If registry exists (`_suggest_scan` absent):**
- Use the registry as-is. Skip to Step 2.

**If registry is missing (`_suggest_scan` present):**
- Call `scan_plugins` silently.
- After scan: plugins that already have a `description.json` will have a proper `usage` field
  — use it directly without any further analysis.
- Plugins with an empty or very short `usage` field (< 10 words) are flagged as "needs description".
- Re-call `load_plugin_registry`.
- Continue to Step 2.

---

## Step 2 — Display plugin directory

Show a compact table — **at most 2 lines per plugin, no raw JSON**:

```
Available plugins (N total):

Plugin               Command                     What it does
─────────────────────────────────────────────────────────────────────
GitHub Planner       /th:github-planner         Plan work, create and track GitHub issues
Plugin Creator       /th:create-plugin          Scaffold a new terminal-hub extension
```

If any plugin lacks a description: show "(no description)" and move on — do not block.

---

## Step 3 — Match intent

If the user describes a task, use `triggers` and `usage` from the registry to match.

| Confidence | Condition | Action |
|------------|-----------|--------|
| High | ≥1 trigger word matches | Suggest immediately: "That's **{plugin}** → `{command}`" |
| Medium | usage overlaps ~50% | Ask one clarifying question, then suggest |
| None | No match | List available commands, offer to help directly |

After any suggestion say: **"Let me know any plans for this!"**

---

## Rules

- Call `load_plugin_registry` once — do not call `scan_plugins` if registry already exists
- Display 1-2 lines per plugin max — no raw fields, no JSON
- Never block on missing descriptions — skip gracefully
- Ask at most one clarifying question before suggesting
