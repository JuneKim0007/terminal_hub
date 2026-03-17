# /t-h:github-planner/analyze

<!-- RULE: Run analysis silently. Report summary counts only, not file contents. -->

Repo analysis workflow:

1. Call `get_setup_status`. If not initialised, run setup first.
2. Call `docs_exist`. If summary < 7 days old, ask: "Project notes exist ({N:.0f}h old). Re-analyze? (yes / use existing)"
3. If analyzing:
   a. Call `analyze_repo_full()` → announce: "Found {total_files} files, fetched {fetched} ({skipped_unchanged} unchanged)."
   b. From the returned `file_index`, generate two documents using the formats below.
      Use `file_index[].exports`, `file_index[].headings`, `file_index[].module_doc` to derive
      content — never request raw file contents. Group files by feature area.
   c. Call `save_project_docs(summary_md, detail_md)`.
4. Say: "Analysis complete. Let me know any plans for this!"

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

## Design Principles
- {Principle extracted from recurring code patterns}

## Known Pitfalls
- {Non-obvious constraint or gotcha}

## Feature Sections
{Comma-separated list matching the H2 headings in project_details.md}
```

The **Feature Sections** line is an index. It lets Claude decide whether to call
`lookup_feature_section` without loading the full detail doc.

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
