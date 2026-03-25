# /th:settings — Conversational Settings Manager

<!-- LOAD ANNOUNCEMENT: At the very start of this command, output exactly:
     🟢 Loaded: th-settings — `extensions/settings/commands/th-settings.md`
     Do this before any tool calls. -->

You are in **settings** mode — view and change all user-configurable values.

---

## Step 1 — Scan configurable values

Scan these sources using the Read and Bash tools:

**Source 1: `terminal_hub/constants.py`**
- Read the file
- Extract every line matching `^[A-Z_]+ = ` (ALL_CAPS assignment)
- For each: record `{name, value, type, description, source: "terminal_hub/constants.py", line_number}`
- Description: the inline comment after `#` on the same line (if any)

**Source 2: All `extensions/*/plugin_config.json` files**
- Run: `find extensions/ -name "plugin_config.json"` to discover them
- For each file: read it and extract all leaf values
- For each leaf: record `{name: "<plugin>.<key_path>", value, type, description: "", source: "<file_path>", key_path: "<dotted.key.path>"}`

**Source 3: `hub_agents/config.yaml`** (if exists)
- Read and extract all leaf values, record with source

---

## Step 2 — Display grouped table

Group values by category and present:

```
⚙ Settings

Testing
  COVERAGE_THRESHOLD    80        minimum coverage % to pass verify step

Model Routing
  MODEL_HAIKU           claude-haiku-4-5-20251001
  MODEL_SONNET          claude-sonnet-4-6
  MODEL_OPUS            claude-opus-4-6

Cache TTLs
  FILE_TREE_TTL         3600      (seconds)
  ISSUES_SYNC_TTL       3600      (seconds)

Analysis
  ANALYSIS_BATCH_SIZE     5
  ANALYSIS_BATCH_SIZE_MAX 20
  ANALYSIS_BATCH_SIZE_MIN 1

Type a setting name or say "change X to Y" to update, or "done" to exit.
```

Category detection rules (apply in order):
- Name contains `COVERAGE` or `THRESHOLD` or `TEST` → Testing
- Name contains `MODEL` or `HAIKU` or `SONNET` or `OPUS` → Model Routing
- Name contains `TTL` or `CACHE` → Cache TTLs
- Name contains `ANALYSIS` or `BATCH` → Analysis
- Otherwise → Other

---

## Step 3 — Handle change requests

When user says "set X to Y", "change X to Y", or "X = Y":

1. Find the setting by name (case-insensitive match)
2. Validate the new value:
   - Integer settings: must be a valid integer; for thresholds (0–100 range) warn if outside
   - String settings (model names): check against known valid values if possible
3. Call `format_prompt(question="Set {NAME} to {new_value}? (was {old_value})", options=["yes", "cancel"], style="confirm")` and print `_display`
4. On **yes**:
   - **`constants.py` values**: use Edit tool to replace exactly the assignment line:
     `old_string: "NAME = {old_value}  # ..."` → `new_string: "NAME = {new_value}  # ..."`
     Preserve the inline comment exactly.
   - **`plugin_config.json` values**: read the JSON, update the key at `key_path`, write back using Write tool (full file rewrite since JSON must stay valid)
   - Re-read the changed line/value to confirm the write succeeded
   - Print: `✅ {NAME} = {new_value} (was {old_value}) — saved to {source_file}`
5. On **cancel**: print "Cancelled." and return to Step 2

---

## Step 4 — Exit

When user says "done" or "exit":
- Print: "Settings session ended."
- No cleanup needed (no caches to clear)

---

## Rules

- **Never rewrite `constants.py` in full** — use Edit tool to change only the specific line
- **Always confirm** with `format_prompt` before writing any value
- **Always re-read** after writing to verify the change landed correctly
- Values that are tuples (`VALID_MODELS`) are read-only — inform the user if they try to change them
