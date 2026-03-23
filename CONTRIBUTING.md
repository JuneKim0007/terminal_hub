# Contributing to terminal-hub

<!-- AUTO-GENERATED: scripts table from pyproject.toml -->
## Available Commands

| Command | Description |
|---------|-------------|
| `pip install -e .` | Editable install — code changes take effect immediately |
| `pytest` | Run test suite with coverage (≥80% required) |
| `pytest -x` | Stop on first failure |
| `pytest tests/tools/` | Run tool-specific tests only |
| `terminal-hub install` | Register MCP server + copy slash commands to Claude Code |
| `terminal-hub verify` | Confirm the server is registered globally |
| `/th:gh-docs` | Create or update README.md + CONTRIBUTING.md, then open a PR or push |
<!-- END AUTO-GENERATED -->

## Environment Variables

<!-- AUTO-GENERATED: env vars from env_store.py / config.py -->
| Variable | Required | Description | Where to set |
|----------|----------|-------------|--------------|
| `GITHUB_TOKEN` | No | GitHub personal access token | Shell env or `hub_agents/.env` |
| `GITHUB_REPO` | No | `owner/repo` for GitHub mode | Set via `setup_workspace` or `hub_agents/.env` |
| `PROJECT_ROOT` | No | Override workspace root detection | Shell env before launching Claude Code |
<!-- END AUTO-GENERATED -->

## Development Setup

```bash
git clone https://github.com/JuneKim0007/terminal_hub.git
cd terminal_hub
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -e .
terminal-hub install          # registers with Claude Code globally
```

**Requirements:** Python 3.10+, Claude Code, GitHub CLI (`gh`) for GitHub features.

## Running Tests

```bash
pytest                         # full suite + coverage report
pytest -x -q                   # fast fail, quiet
pytest tests/tools/test_file_tree.py   # single file
```

Coverage gate: **80% minimum** (configured in `pyproject.toml`). The gate runs on every `pytest` invocation.

## Writing Tests

- All tests live under `tests/`
- Use `tmp_path` pytest fixture for isolated workspace setup
- Patch `extensions.gh_management.github_planner.get_workspace_root` for tests needing a workspace root
- Patch `extensions.gh_management.github_planner._get_github_client` for tests that would hit GitHub API
- MCP tool tests use `server._tool_manager.call_tool(name, args)` via `asyncio.run()`
- Clear module-level caches in `autouse` fixtures: `_ANALYSIS_CACHE`, `_PROJECT_DOCS_CACHE`, `_FILE_TREE_CACHE`, `_SESSION_HEADER_CACHE`

## Project Structure

```
terminal_hub/           core server + framework (no GitHub dependency)
extensions/             all plugins live here
  gh_management/        GitHub management plugins
    github_planner/     planning, analysis, issue management (~55 MCP tools)
    gh_implementation/  issue implementation lifecycle (~10 tools)
  plugin_creator/       conversational plugin scaffolding
  plugin_customization/ model routing (dispatch_task)
  builtin/              built-in slash commands (help, active, converse)
tests/                  all tests (mirrors source layout)
  tools/                MCP tool integration tests
hub_agents/             runtime workspace state (gitignored, per-project)
docs/                   user/ and dev/ documentation
```

## PR Checklist

- [ ] `pytest` passes with ≥80% coverage
- [ ] New public functions have docstrings
- [ ] New tools registered in `register(mcp)` via `@mcp.tool()`
- [ ] No hardcoded paths — use `_gh_planner_docs_dir(root)` for plugin output paths
- [ ] Cache entries keyed by workspace root or repo, not global singletons
- [ ] `encoding="utf-8"` on all `read_text()` / `write_text()` calls
- [ ] Atomic writes via `tmp.write_text(...); os.replace(tmp, dest)`

## Extending terminal-hub

See `README.md` → "Writing an extension" for the plugin API contract.
See `extensions/gh_management/github_planner/` as the reference implementation.

For full detail:
- [Adding a Plugin](docs/dev/adding-a-plugin.md) — complete step-by-step guide with working example
- [Testing](docs/dev/testing.md) — test patterns, coverage gate, and how to run the test suite
