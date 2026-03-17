# /t-h:github-planner/analyze

<!-- RULE: Run analysis silently. Report summary counts only, not file contents. -->

Repo analysis workflow:

1. Call `get_setup_status`. If not initialised, run setup first.
2. Call `docs_exist`. If summary < 7 days old, ask: "Project notes exist ({N:.0f}h old). Re-analyze? (yes / use existing)"
3. If analyzing:
   a. Call `analyze_repo_full()` → announce: "Found {total_files} files, fetched {fetched} ({skipped_unchanged} unchanged)."
   b. From the returned `file_index`, generate:
      - `project_summary.md` (≤400 tokens: description + tech stack table + pitfalls)
      - `project_detail.md` (per-file: purpose, exports, behaviour, workflows)
      Use `file_index[].exports`, `file_index[].headings`, `file_index[].module_doc` — never request raw file contents.
   c. Call `save_project_docs(summary_md, detail_md)`.
4. Say: "Analysis complete. Let me know any plans for this!"
