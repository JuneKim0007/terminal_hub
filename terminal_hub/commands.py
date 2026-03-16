"""Centralized command and endpoint definitions.

All GitHub API paths and gh CLI command templates live in hub_commands.json.
Import endpoint() to resolve a named command to its method + URL template.
"""
import json
from pathlib import Path

_CMDS: dict[str, dict[str, str]] = {}


def _load() -> None:
    global _CMDS
    path = Path(__file__).parent / "hub_commands.json"
    _CMDS = json.loads(path.read_text())


_load()


def endpoint(section: str, name: str) -> tuple[str, str]:
    """Return (HTTP_METHOD, path_template) for the named command.

    Example:
        method, path = endpoint("github", "create_issue")
        # method="POST", path="/repos/{repo}/issues"
    """
    raw = _CMDS[section][name]
    method, path = raw.split(" ", 1)
    return method, path


def gh_cmd(name: str) -> str:
    """Return the gh CLI command string for *name*."""
    return _CMDS["gh_cli"][name]
