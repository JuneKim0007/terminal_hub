# AGENT_WORKFLOW: Scattered File Cleanup

> **This document is for LLM/agent use.** Follow every step in order.
> Do not skip or reorder steps. Check off each item before moving on.

---

## 0. Understand the Project Layout First

Before touching any file, build a mental model of what _should_ exist:

```
terminal_hub/        ← Python package: server, storage, auth, install, config, env_store
extensions/          ← Plugin packages loaded at runtime via register(mcp)
  github_planner/    ← gh-planner plugin: analyzer, storage, __init__ (tools)
    commands/        ← command .md files for agents
    commands/github-planner/  ← sub-command .md files
  plugin_creator/    ← plugin-creator plugin
  *.json             ← extension registry / config files
commands/            ← global command overrides (user-only, mostly empty)
tests/               ← ALL test files must live here
docs/                ← living documentation only (not old specs)
hub_agents/          ← GITIGNORED runtime output (never committed)
```

Design principle: **one canonical location per concern**. Duplicates are always wrong.

---

## 1. Read Before Acting

For each file you plan to change or delete:

1. Read the file (`Read` tool).
2. Ask: "Is this a duplicate, stale reference, or wrong location?"
3. Identify the **canonical version** to keep.
4. Record your decision in a comment before executing.

---

## 2. Cleanup Checklist

Work through items in this order (easiest → most impactful):

### 2a. Delete root-level `test_prototype.py`
- Read the file first.
- If it contains unique tests not covered in `tests/`, move the tests to an appropriate file under `tests/`.
- If fully redundant, delete it.
- Run `pytest` after deletion to confirm tests still pass.

### 2b. Remove empty placeholder directories
- `commands/user/` contains only `.gitkeep` → remove `.gitkeep`, then remove the directory if empty.
- Check `extensions/user/` — if it exists and is empty, do the same.
- Neither directory has any active use; they were scaffolding leftovers.

### 2c. Delete `terminal_hub/labels.json` (duplicate)
- Canonical copy: `extensions/github_planner/labels.json`
- Grep for any imports of `terminal_hub/labels.json` or `labels.json` from within `terminal_hub/`.
- If no imports reference the `terminal_hub/` copy, delete it.
- Run `pytest` after deletion.

### 2d. Delete `terminal_hub/hub_commands.json` (duplicate)
- Canonical copy: `extensions/github_planner/hub_commands.json`
- Same process as 2c.

### 2e. ~~Update stale paths in descriptor JSONs~~ (DONE)
- `default.analyzer.json` and `prompt_debugger.json` moved to `extensions/github_planner/` with correct paths.
- Skip this step.

### 2g. Deduplicate `commands/setup.md` vs `commands/github-planner/setup.md`
- Read both files.
- If identical: delete `extensions/github_planner/commands/setup.md` (the flat one), keep `github-planner/setup.md`.
- If different: diff them and merge into `github-planner/setup.md`, then delete the flat one.
- Grep for any references to the deleted path in other `.md` files.

### 2h. Check and deduplicate `commands/auth.md` vs `commands/github-planner/auth.md`
- Same process as 2g.

### 2i. Delete or archive `docs/superpowers/specs/2026-03-15-terminal-hub-design.md`
- Read it briefly. If the design is superseded by `PLAN.md` or current code, delete it.
- If it contains unique decisions not recorded elsewhere, move relevant sections to `docs/`.

---

## 3. Verify After Each Change

After every file deletion or modification:

```bash
pytest
```

If tests fail → revert the last change with `git checkout -- <file>`, investigate, then retry with a safer approach.

---

## 4. Commit

Once all items are checked off and tests are green:

```bash
git add -A
git commit -m "chore: remove duplicate and stale files from repo"
```

Then close the GitHub issue.

---

## Anti-Patterns to Avoid

- **Do not delete anything before reading it.**
- **Do not batch all deletions into one step** — do one at a time with test verification.
- **Do not update stale paths by guessing** — check `extensions/github_planner/storage.py` for the authoritative path constants.
- **Do not touch `hub_agents/`** — it is gitignored runtime output, not a source file.
