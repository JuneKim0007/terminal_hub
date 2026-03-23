---
name: create-dev-readme-docs
description: Rules for writing developer and contributor documentation — CONTRIBUTING.md, TECH_STACK.md, and docs/dev/* pages. Specifies which local files to read (plugin_loader.py, server.py, register(mcp) pattern, test structure), the contributor doc structure, plugin-authoring guide conventions, and GitHub navigation layout. Load when writing docs for developers or contributors.
alwaysApply: false
triggers:
  - contributing docs
  - developer docs
  - CONTRIBUTING.md
  - architecture docs
  - plugin authoring guide
  - dev documentation
  - tech stack
---

# create-dev-readme-docs Skill

Rules for writing developer and contributor documentation for terminal-hub.

## When to Use

- Writing `CONTRIBUTING.md`, `TECH_STACK.md`, architecture docs, or plugin-authoring guides
- Writing `docs/dev/` pages for contributors or developers extending the system
- Any documentation targeting someone building or modifying terminal-hub, not using it

## When NOT to Use

- Writing end-user `README.md`, `QUICKSTART.md`, or usage docs → use `create-user-readme-docs` skill
- Writing skill files → use `create-skill` skill

---

## Section 2 — Local Files to Read (ordered, with what to extract)

Always read in this priority order before writing any dev doc:

### Priority 1 — Architecture and entry points (always read first)
```
terminal_hub/plugin_loader.py
  → discover_plugins(plugins_dir): globs extensions/*/plugin.json + extensions/*/*/plugin.json
  → validate_manifest(): required fields = {name, version, entry, commands_dir, commands}
  → load_plugin(manifest, mcp): importlib.import_module(manifest["entry"]); module.register(mcp)
  → build_instructions(plugins): builds MCP server instructions string from manifests + description.json

terminal_hub/server.py (first 80 lines)
  → create_server(): FastMCP("terminal-hub", instructions=...) setup
  → Plugin loading loop: discover_plugins(extensions/) → for each: load_plugin(manifest, mcp)
  → Core tool registration happens in server.py before plugin tools
  → Plugin loading order: gh_management/github_planner, gh_management/gh_implementation, plugin_creator

terminal_hub/__main__.py
  → CLI: terminal-hub install (copies to ~/.claude/commands/ via run_install())
  → CLI: terminal-hub verify (checks ~/.claude/commands/ via run_verify())
  → Default (no args): create_server().run() — MCP stdio mode
```

### Priority 2 — Plugin authoring pattern
```
extensions/gh_management/github_planner/plugin.json
  → Required fields: name, version, description, entry, commands_dir, commands
  → Optional fields: requires_env, optional_env, conversation_triggers, entry_command
  → Example entry: "extensions.gh_management.github_planner"
  → conversation_triggers: list of phrases that prompt Claude to offer this plugin

extensions/gh_management/github_planner/__init__.py (lines 1–60, register(mcp) start)
  → Module-level state pattern: _PROJECT_DOCS_CACHE, _SESSION_FLAGS (dict keyed by str(root))
  → register(mcp): all tools defined as @mcp.tool() nested functions inside register(mcp)
  → Import from storage: from extensions.gh_management.github_planner.storage import write_issue_file
  → Helper pattern: _do_foo() private function + public foo() tool wrapper

extensions/gh_management/github_planner/storage.py (first 80 lines)
  → _atomic_write(path, content): write to .tmp file, os.replace — ALWAYS use this for file writes
  → write_issue_file(): full YAML frontmatter + body assembly pattern
  → read_issue_frontmatter(): YAML parse with OSError/YAMLError guard

extensions/gh_management/gh_implementation/__init__.py (lines 1–50)
  → Cross-plugin import pattern: from extensions.gh_management.github_planner import get_workspace_root
  → Minimal plugin that depends on another — do NOT use relative imports between plugins
```

### Priority 3 — Existing contributor docs (update not replace)
```
CONTRIBUTING.md       → read current content; extend not duplicate
TECH_STACK.md         → existing architecture notes; link rather than rewrite
hub_agents/hub_agents/extensions/gh_planner/project_summary.md
                      → project goals and design principles (if exists)
```

### Priority 4 — Test structure and CI
```
pyproject.toml        → [tool.pytest.ini_options]: testpaths=["tests"], addopts includes
                         --cov --cov-fail-under=80, coverage source=["terminal_hub","extensions"]
tests/                → ~870 tests across: test_workflows.py, test_connected_docs.py,
                         test_storage.py, tools/test_create_issue.py, tools/test_gh_implementation.py
terminal_hub/errors.py → BaseHubError, ToolError, ConfigError patterns for new plugins
```

### Priority 5 — Slash commands and skills layout (for plugin authors)
```
extensions/gh_management/github_planner/commands/
  → .md files are slash commands loaded verbatim into Claude's context
  → Each file = one command; filename without .md = command stem
  → Use <!-- RULE: ... --> comments at top to inject behaviour rules
extensions/gh_management/github_planner/description.json
  → subcommands catalogue: command, aliases, use_when
  → entry.triggers: conversation phrases that activate the plugin
extensions/gh_management/github_planner/skills/
  → Two-tier skill system: plugin-level skills here, project-level in hub_agents/skills/
  → SKILLS.md: always-loaded registry (alwaysApply: true)
  → Individual skill files: alwaysApply: false, loaded on demand via load_skill("name")
```

---

## Section 3 — docs/dev/ Directory Structure

When writing developer docs, create this layout if absent:

```
docs/
├── dev/
│   ├── index.md              ← overview of dev docs + links to sub-pages
│   ├── architecture.md       ← system design: MCP, FastMCP, plugin loader, server.py flow
│   ├── adding-a-plugin.md    ← step-by-step plugin authoring guide (most important page)
│   ├── commands.md           ← how slash command .md files work, <!-- RULE: --> comments
│   ├── testing.md            ← test setup, coverage gate, patterns, running tests
│   └── skills-system.md      ← two-tier skill system — Tier 1 plugin, Tier 2 project
```

---

## Section 4 — CONTRIBUTING.md Structure (medium-large OSS)

terminal-hub is a **medium-large** project (MCP server, plugin architecture, ~870 tests). Apply this 8-section structure:

```
1. # Contributing to terminal-hub

2. ## Development Setup  ← exact commands with code blocks
   git clone https://github.com/JuneKim0007/terminal_hub
   cd terminal_hub
   pip install -e .
   terminal-hub install
   terminal-hub verify

3. ## Running Tests
   python -m pytest tests/
   # Coverage gate: --cov-fail-under=80 enforced automatically
   # Run a specific test file:
   python -m pytest tests/test_workflows.py -v

4. ## Project Structure  ← annotated directory tree
   terminal_hub/        ← core: server.py, plugin_loader.py, workspace.py, __main__.py
   extensions/          ← all plugins live here
     builtin/           ← built-in slash commands (help.md, active.md, converse.md)
     gh_management/     ← GitHub plugins
       github_planner/  ← planning + analysis tools (~55 MCP tools)
       gh_implementation/ ← issue implementation tools
     plugin_creator/    ← conversational plugin scaffolding
     plugin_customization/ ← model routing (dispatch_task)
   tests/               ← mirrors source structure; ~870 tests
   hub_agents/          ← runtime workspace state (gitignored)
   docs/                ← documentation

5. ## Adding a Plugin  ← the core contributor path
   Step 1: Create extensions/my_plugin/ directory
   Step 2: Write plugin.json (required: name, version, entry, commands_dir, commands)
   Step 3: Write __init__.py with register(mcp) function using @mcp.tool()
   Step 4: Add commands/*.md slash command files
   Step 5: Write tests in tests/ mirroring your plugin structure
   Step 6: Run python -m pytest tests/ and verify coverage ≥ 80%
   → See docs/dev/adding-a-plugin.md for the full annotated example

6. ## Code Style
   Python 3.10+ — use | for Union types (str | None, not Optional[str])
   No mutable global state outside module-level cache dicts keyed by str(root)
   Implementation in _private functions; public @mcp.tool() wrappers only
   All tool functions return dict with _display field (user-visible one-liner)
   File I/O: always use _atomic_write() from storage — never write files directly
   Cross-plugin imports: use full module path (from extensions.gh_management.github_planner import ...)

7. ## Pull Requests
   Branch from main, keep PRs focused on one logical change
   Tests must pass with coverage ≥ 80%
   Commit messages: "type: description (#issue)" format

8. ## Architecture Reference  ← link to docs/dev/architecture.md
   See docs/dev/architecture.md for the full MCP + plugin loader flow.
```

---

## Section 5 — Plugin Authoring Rules

Exact patterns new plugin authors must follow:

### Rule 1: plugin.json required fields
```json
{
  "name": "my_plugin",
  "version": "0.1",
  "description": "What this plugin does — one sentence, shown in Claude's context",
  "entry": "extensions.my_plugin",
  "commands_dir": "commands",
  "commands": ["main.md"],
  "conversation_triggers": ["trigger phrase 1", "trigger phrase 2"]
}
```
Fields `requires_env`, `optional_env`, `entry_command` are optional.

### Rule 2: register(mcp) is the only required function
```python
from mcp.server.fastmcp import FastMCP

def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def my_tool(param: str) -> dict:
        """Describe what this tool does — Claude reads this as the tool description."""
        return {"result": param.upper(), "_display": f"✅ Done: {param}"}
```

### Rule 3: All tools must return dict with `_display`
```python
# Bad — returns bare value
def bad_tool(name: str) -> str:
    return f"Hello {name}"

# Good — returns dict with _display
def good_tool(name: str) -> dict:
    return {"greeting": f"Hello {name}", "_display": f"✅ Greeted {name}"}
```

### Rule 4: Cross-plugin imports use full module path
```python
# Good — full module path
from extensions.gh_management.github_planner import get_workspace_root

# Bad — relative imports between plugins WILL break
from ..github_planner import get_workspace_root  # DO NOT DO THIS
```

### Rule 5: Session state uses module-level dicts keyed by str(root)
```python
_MY_CACHE: dict[str, Any] = {}  # keyed by str(root) → supports multiple projects

def _get_cached(root: Path) -> dict:
    return _MY_CACHE.setdefault(str(root), {})
```

### Rule 6: File writes must use _atomic_write
```python
from extensions.gh_management.github_planner.storage import _atomic_write
# or define your own — always write to .tmp then os.replace:
def _atomic_write(path: Path, content: str) -> None:
    import os, tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(tmp_fd, "w") as f:
        f.write(content)
    os.replace(tmp_path, path)
```

---

## Section 6 — Writing Rules for Dev Docs

1. **Show exact commands — never "install the dependencies"**
   - Bad:  `"Install dependencies"`
   - Good: `pip install -e . && terminal-hub install`

2. **Every code example must be runnable** — use real module paths, not pseudocode
   - Bad:  `"Create a register function that adds a tool..."`
   - Good:
     ```python
     def register(mcp: FastMCP) -> None:
         @mcp.tool()
         def hello(name: str) -> dict:
             return {"_display": f"Hello {name}"}
     ```

3. **Architecture descriptions lead with data flow, not file names**
   - Bad:  `"plugin_loader.py handles loading"`
   - Good: `"On startup: server.py calls discover_plugins(extensions/) → globs extensions/*/plugin.json → for each valid manifest: importlib.import_module(manifest['entry']); module.register(mcp)"`

4. **Test section must state the coverage gate explicitly**
   - `"Tests must pass with coverage ≥ 80% — pytest enforces this via --cov-fail-under=80 in pyproject.toml"`

5. **"Adding a Plugin" is the most important contributor path** — write it as the longest section with a complete working minimal example (plugin.json + __init__.py + one command file + one test)

6. **Never say "see the source code"** — embed the key patterns inline in the doc. The developer should not need to read source to understand the conventions.

---

## Section 7 — Before/After Examples

### Example 1: Weak plugin.json → Strong one

**Before (weak, missing triggers):**
```json
{"name": "my_plugin", "entry": "extensions.my_plugin", "commands": ["main.md"]}
```

**After (complete):**
```json
{
  "name": "my_plugin",
  "version": "0.1",
  "description": "Does X — what this plugin does in one sentence",
  "entry": "extensions.my_plugin",
  "commands_dir": "commands",
  "commands": ["main.md"],
  "conversation_triggers": ["do X", "start X workflow"]
}
```

### Example 2: register(mcp) without _display → Correct pattern

**Before (wrong — no _display):**
```python
def register(mcp):
    @mcp.tool()
    def process(data: str) -> str:
        return data.upper()
```

**After (correct):**
```python
from mcp.server.fastmcp import FastMCP

def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def process(data: str) -> dict:
        """Process data by uppercasing it. Returns processed result."""
        result = data.upper()
        return {"result": result, "_display": f"✅ Processed: {result[:40]}"}
```

### Example 3: Vague Project Structure → Annotated tree

**Before (vague):**
```
The project has terminal_hub/ and extensions/ directories.
```

**After (annotated):**
```
terminal_hub/           ← core server and infrastructure
  server.py             ← FastMCP setup, plugin loading loop, core tools
  plugin_loader.py      ← discover_plugins(), load_plugin(), build_instructions()
  __main__.py           ← CLI: install / verify / stdio server
  workspace.py          ← hub_agents/ path resolution
extensions/             ← all plugins — each directory = one plugin
  gh_management/        ← GitHub management plugins (consolidated namespace)
    github_planner/     ← ~55 MCP tools for planning, analysis, issue management
    gh_implementation/  ← ~10 tools for issue implementation lifecycle
  plugin_creator/       ← conversational plugin scaffolding tools
tests/                  ← ~870 tests; mirrors source layout
hub_agents/             ← runtime workspace state — gitignored, per-project
docs/                   ← user/ and dev/ documentation
```
