"""Plugin creator for terminal-hub.

Provides tools for scaffolding new plugins: writing files, generating tests,
and validating the result before declaring it ready.
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

from terminal_hub.plugin_loader import validate_manifest
from terminal_hub.workspace import resolve_workspace_root

_EXTENSIONS_ROOT = Path(__file__).parent.parent  # extensions/
_TESTS_ROOT = _EXTENSIONS_ROOT.parent / "tests"   # tests/


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_plugin_name(name: str) -> bool:
    """Return True if name is a valid Python identifier (hyphens/underscores ok)."""
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", name))


def _plugin_dir(name: str) -> Path:
    return _EXTENSIONS_ROOT / name


# ── Tool implementations ──────────────────────────────────────────────────────

def _do_write_plugin_file(plugin_name: str, filename: str, content: str) -> dict:
    """Write a file inside plugins/<plugin_name>/."""
    if not _safe_plugin_name(plugin_name):
        return {"error": "invalid_name",
                "message": f"Plugin name {plugin_name!r} is not a valid identifier."}

    # Prevent path traversal
    dest = (_plugin_dir(plugin_name) / filename).resolve()
    allowed_root = _plugin_dir(plugin_name).resolve()
    if not str(dest).startswith(str(allowed_root)):
        return {"error": "path_traversal",
                "message": "filename must not escape the plugin directory."}

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return {"written": True, "path": str(dest.relative_to(_EXTENSIONS_ROOT.parent))}


def _do_write_test_file(plugin_name: str, content: str) -> dict:
    """Write tests/test_<plugin_name>.py."""
    if not _safe_plugin_name(plugin_name):
        return {"error": "invalid_name",
                "message": f"Plugin name {plugin_name!r} is not a valid identifier."}

    safe_name = plugin_name.replace("-", "_")
    dest = _TESTS_ROOT / f"test_{safe_name}.py"
    dest.write_text(content, encoding="utf-8")
    return {"written": True, "path": f"tests/test_{safe_name}.py"}


def _do_validate_plugin(plugin_name: str) -> dict:
    """Validate that plugins/<plugin_name>/ forms a loadable plugin.

    Checks:
    1. plugin.json exists and passes validate_manifest()
    2. entry module is importable
    3. entry module has a callable register attribute
    4. description.json exists
    5. All command files listed in plugin.json are present on disk

    Returns {valid: bool, errors: [str]}.
    """
    errors: list[str] = []
    plugin_dir = _plugin_dir(plugin_name)

    if not plugin_dir.exists():
        return {"valid": False, "errors": [f"plugins/{plugin_name}/ does not exist"]}

    # 1. plugin.json
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        errors.append("plugin.json is missing")
        return {"valid": False, "errors": errors}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"plugin.json is invalid JSON: {exc}")
        return {"valid": False, "errors": errors}

    manifest_errors = validate_manifest(manifest)
    errors.extend(manifest_errors)

    # 2. entry module importable
    # #62 — inject project root so newly-written plugins can be imported
    entry = manifest.get("entry", "")
    if entry:
        project_root = str(_EXTENSIONS_ROOT.parent)
        injected = project_root not in sys.path
        if injected:
            sys.path.insert(0, project_root)
        try:
            mod = importlib.import_module(entry)
        except SyntaxError as exc:
            errors.append(
                f"entry module {entry!r} has a syntax error: {exc} "
                f"(hint: check for syntax errors in __init__.py)"
            )
            mod = None
        except Exception as exc:
            errors.append(f"entry module {entry!r} is not importable: {exc}")
            mod = None
        finally:
            if injected and project_root in sys.path:
                sys.path.remove(project_root)

        # 3. register(mcp) present and callable
        if mod is not None:
            reg = getattr(mod, "register", None)
            if reg is None:
                errors.append(f"entry module {entry!r} has no 'register' attribute")
            elif not callable(reg):
                errors.append(f"entry module {entry!r}: 'register' is not callable")

    # 4. description.json
    if not (plugin_dir / "description.json").exists():
        errors.append("description.json is missing (required for plugin awareness)")

    # 5. command files
    commands_dir_name = manifest.get("commands_dir", "commands")
    commands_dir = plugin_dir / commands_dir_name
    for cmd in manifest.get("commands", []):
        if not (commands_dir / cmd).exists():
            errors.append(f"command file {commands_dir_name}/{cmd} is missing")

    return {"valid": len(errors) == 0, "errors": errors}


# ── Plugin registration ────────────────────────────────────────────────────────

def register(mcp) -> None:
    """Register plugin_creator tools on the given FastMCP instance."""

    @mcp.tool()
    def write_plugin_file(plugin_name: str, filename: str, content: str) -> dict:
        """Write a file inside plugins/<plugin_name>/.

        plugin_name: identifier for the new plugin (e.g. 'my_plugin').
        filename: relative path within the plugin dir (e.g. 'commands/start.md').
        content: full file content as a string.
        Creates parent directories as needed.
        """
        return _do_write_plugin_file(plugin_name, filename, content)

    @mcp.tool()
    def write_test_file(plugin_name: str, content: str) -> dict:
        """Write tests/test_<plugin_name>.py for the new plugin.

        Generates the test file in the project's tests/ directory.
        Must include at minimum: test_register_is_callable, test_register_does_not_raise.
        """
        return _do_write_test_file(plugin_name, content)

    @mcp.tool()
    def validate_plugin(plugin_name: str) -> dict:
        """Validate that plugins/<plugin_name>/ forms a loadable plugin.

        Checks: plugin.json validity, entry module importability, register(mcp)
        presence, description.json existence, and command file completeness.
        Returns {valid: bool, errors: [str]}.
        Call as the final step of the create_plugin workflow; fix any errors before
        declaring the plugin ready.
        """
        return _do_validate_plugin(plugin_name)
