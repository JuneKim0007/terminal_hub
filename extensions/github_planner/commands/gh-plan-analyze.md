# /th:gh-plan-analyze

<!-- RULE: Run analysis silently. Report summary counts only, not file contents. -->

Repo analysis workflow:

1. Call `get_setup_status`. If not initialised, run setup first.
2. **Scan profile check (#149):** Call `get_scan_profile_status()`. Print `_display` verbatim.
   - `exists: true` → proceed (profile controls which files are analyzed)
   - `needs_creation: true` → ask user *(yes / customize / skip)*:
     - "yes" → call `create_scan_profile()` (default profile)
     - "customize" → show default content, wait for edits, call `create_scan_profile(content=...)`
     - "skip" → proceed without a profile (uses built-in extension filter)
3. Call `docs_exist`. If summary < 7 days old, ask: "Project notes exist ({N:.0f}h old). Re-analyze? (yes / use existing)"
4. If analyzing:
   a. Call `analyze_repo_full()` → announce: "Found {total_files} files, fetched {fetched} ({skipped_unchanged} unchanged, {excluded_by_profile} excluded by profile)."
   b. **Existing docs detection** (#84): from `file_index`, identify doc-like .md files
 from `file_index`, identify doc-like .md files
      (paths matching: README*, docs/*, DESIGN*, ARCHITECTURE*, SPEC*, CONTRIBUTING*, CHANGELOG*).
      If any found, present them:
      ```
      Found existing documentation:
        - README.md (1.2KB)
        - docs/DESIGN.md (3.4KB)
      How should I handle these?
      a) Refer to them — read and incorporate their content
      b) Overwrite — replace with TH-generated project_summary + project_detail
      c) Merge — combine existing + analysis into new TH docs
      d) Ignore — create TH docs independently
      ```
      Save the strategy to `hub_agents/extensions/gh_planner/docs_strategy.json`:
      `{"strategy": "refer|overwrite|merge|ignore", "referred_docs": [...]}`
      If strategy is **refer**: note the paths; Claude reads them before generating TH docs.
      If strategy is **ignore** or no docs found: proceed directly to step (c).
   c. From the returned `file_index`, generate two documents using the formats below.
      Use `file_index[].exports`, `file_index[].headings`, `file_index[].module_doc` to derive
      content — never request raw file contents. Group files by feature area.
   d. Call `save_project_docs(summary_md, detail_md)`.
5. Say: "Analysis complete. Let me know any plans for this!"

---

## project_summary.md format (≤500 tokens)

```
# {Project name}
{1–2 sentence description}

## Tech Stack
| Layer | Technology |
|-------|------------|

## Implemented Features
- {Feature A}: {one-line description}
- {Feature B}: {one-line description}

## Interface Layers
| Layer | Description |
|-------|-------------|
| {name} | {what lives here — key files, inputs, outputs} |

## Design Principles
- {Principle extracted from recurring code patterns}
- File loading: lazy and partial — load a file only when decided relevant; fetch only the needed section, never the whole file
- Task dispatch: file-location / scan / classification → lightweight model (Haiku) via dispatch_task; simple writes → Python MCP call directly; analysis / planning → standard model (Sonnet)

## Known Pitfalls
- {Non-obvious constraint or gotcha}

## Planned Features
*(populated automatically as issues are created)*
```

**Interface Layers guidance:** Derive from the tech stack and code structure. Examples:
- Web app: `Frontend` (React/templates) → `API` (routes/controllers) → `Services` (business logic) → `Storage` (DB/files)
- CLI tool: `Commands` (entry points) → `Core Logic` (processing) → `Adapters` (external APIs/files)
- MCP server: `MCP Tools` (public surface) → `Extension Logic` (per-plugin handlers) → `Storage` (config/issues/cache)
Keep layer names short (1–2 words). Description = one sentence about what code lives there.

<!-- NOTE: Do NOT add a "Feature Sections" line — it goes stale when project_detail.md is edited.
     Use get_session_header() which returns the live sections list from project_detail.md. -->

---

## project_details.md format (feature-area design dictionary)

One H2 section per distinct feature area (e.g. "Issue Management", "Plugin Framework",
"Auth", "Session Context"). Group related files under the same heading.

```markdown
## {Feature Area Name}

### Existing Design
- Data model / storage path
- Key functions/tools and their contracts (inputs → outputs)
- Notable constraints or invariants

### Extension Guidelines
- Patterns new features in this area must follow
- Anti-patterns already observed — avoid these
- Where to add new code (module / file)
```

Each section is independently retrievable via `lookup_feature_section`. Keep sections
focused; a file may appear in multiple sections if relevant.
