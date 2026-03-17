# /t-h:create-plugin

<!-- RULE: Guide the user conversationally. Write files only after user confirms each step. Call validate_plugin as the final step and fix any reported errors before declaring done. -->

Plugin creation workflow:

## Step 1 — Name and purpose
Ask:
- "What should the plugin be called? (e.g. `my_plugin` — alphanumeric, hyphens/underscores ok)"
- "What does this plugin do in one sentence?"
- "What namespace should commands install under? Default is `t-h` (so commands will be `/t-h:<plugin-name>/...`). Press enter to accept or type a different namespace."

## Step 2 — Commands
Ask: "What slash commands should this plugin provide? List them one per line (e.g. `start.md`, `list.md`)."

For each command, ask: "What phrases should make me suggest `/<namespace>:<command>`? (e.g. 'deploy to staging', 'check build')"

## Step 3 — Write plugin.json
Call `write_plugin_file(plugin_name, "plugin.json", ...)` with:
```json
{
  "name": "<plugin_name>",
  "version": "1.0",
  "entry": "plugins.<plugin_name>",
  "install_namespace": "<namespace>",
  "entry_command": "<first_command>.md",
  "commands_dir": "commands",
  "commands": ["<command1>.md", ...],
  "description": "<one-line description>",
  "conversation_triggers": [<phrases from step 2>]
}
```

## Step 4 — Write description.json
Call `write_plugin_file(plugin_name, "description.json", ...)`:
```json
{
  "plugin": "<plugin_name>",
  "install_namespace": "<namespace>",
  "entry": {
    "command": "/<namespace>:<entry_command_stem>",
    "use_when": "<description>"
  },
  "subcommands": [
    {
      "command": "/<namespace>:<command_stem>",
      "aliases": [<phrases from step 2>],
      "use_when": "<when to suggest this command>"
    }
  ]
}
```

## Step 5 — Write __init__.py
Call `write_plugin_file(plugin_name, "__init__.py", ...)` with:
```python
"""<Description> plugin for terminal-hub."""

def register(mcp) -> None:
    """Register all <plugin_name> tools on the given FastMCP instance."""

    @mcp.tool()
    def <first_tool>() -> dict:
        """<docstring>"""
        return {"status": "ok"}
```

## Step 6 — Write command files
For each command, call `write_plugin_file(plugin_name, "commands/<command>.md", ...)` with a skeleton:
```markdown
# /<namespace>:<command_stem>

<!-- TODO: describe what this command does -->

1. ...
```

## Step 7 — Write test scaffold
Call `write_test_file(plugin_name, ...)` with:
```python
"""Smoke tests for <plugin_name> plugin."""
import pytest
from unittest.mock import MagicMock
from plugins.<plugin_name> import register


def test_register_is_callable():
    assert callable(register)


def test_register_does_not_raise():
    """register(mcp) should not raise on a bare MagicMock."""
    register(MagicMock())
```

## Step 8 — Validate
Call `validate_plugin(plugin_name)`. If `valid` is False, fix each reported error before continuing.

## Step 9 — Done
Say: "Plugin `<plugin_name>` is ready. Run `terminal-hub install` to install its commands. Let me know any plans for this!"
