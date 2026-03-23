# Testing

Test setup, coverage requirements (≥ 80%), and testing patterns for terminal-hub.

---

## Running tests

```bash
# Full suite with coverage
pytest

# Fast run, no coverage gate
pytest --no-cov

# Specific file
pytest tests/tools/test_docs_map.py --no-cov

# With verbose output
pytest -v
```

Coverage is configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=terminal_hub --cov=extensions --cov-report=term-missing --cov-fail-under=80"
```

The `--cov-fail-under=80` gate runs on the full suite. Running a single test file without `--no-cov` will show low coverage for the whole codebase — that's expected, not a failure.

---

## Test file layout

```
tests/
└── tools/
    └── test_<tool_name>.py    # one file per MCP tool or tool group
```

Example: `tests/tools/test_docs_map.py` covers `build_docs_map` and `get_docs_map`.

---

## Calling MCP tools in tests

```python
import asyncio
from terminal_hub.server import create_server

def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))

def test_my_tool():
    server = create_server()
    result = call(server, "my_tool", {"input": "hello"})
    assert result["_display"] == "✅ Done: HELLO"
```

---

## The _do_* pattern

Business logic lives in `_do_*` private functions. Test these directly for fast unit tests without going through the MCP layer:

```python
# In the plugin:
def register(mcp) -> None:
    @mcp.tool()
    def build_docs_map() -> dict:
        return _do_build_docs_map()

    def _do_build_docs_map() -> dict:
        # actual logic here

# In the test:
from extensions.gh_management.github_planner import _do_build_docs_map

def test_build_docs_map_finds_skills(plugin_dir):
    with patch("extensions.gh_management.github_planner._PLUGIN_DIR", plugin_dir):
        result = _do_build_docs_map()
    assert "my_skill" in result["skills"]
```

---

## Filesystem mocking

Most tools write to or read from `hub_agents/` in the user's project root. Patch `get_workspace_root` to redirect writes to a `tmp_path`:

```python
from unittest.mock import patch

@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path

def test_something(workspace):
    with patch("extensions.gh_management.github_planner.get_workspace_root",
               return_value=str(workspace)):
        result = _do_something()
    assert (workspace / "hub_agents" / "output.json").exists()
```

For tools that read from the plugin directory (skills, commands), patch `_PLUGIN_DIR` and `_COMMANDS_DIR`:

```python
def test_docs_map(plugin_dir):
    with patch("extensions.gh_management.github_planner._PLUGIN_DIR", plugin_dir), \
         patch("extensions.gh_management.github_planner._COMMANDS_DIR",
               plugin_dir / "commands"):
        result = _do_build_docs_map()
```

---

## What NOT to test

- FastMCP registration internals — `register(mcp)` wiring is framework behaviour
- MCP protocol serialisation
- GitHub API responses (mock at the HTTP layer, not the tool layer)
- `terminal-hub install` / `terminal-hub verify` CLI commands (covered by integration tests only)

---

## Coverage omissions

`terminal_hub/__main__.py` is excluded from coverage (`omit` in `pyproject.toml`) — it's a thin CLI entry point with no testable logic.
