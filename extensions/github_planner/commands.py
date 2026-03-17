"""Centralized command and endpoint definitions.

All GitHub API paths live in hub_commands.json.
Import endpoint() to resolve a named command to its method + URL template.
"""
import json
from pathlib import Path

_CMDS: dict[str, dict[str, str]] = {}


def _load() -> None:
    global _CMDS
    path = Path(__file__).parent / "hub_commands.json"
    try:
        _CMDS = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to load hub_commands.json: {exc}") from exc


_load()


def endpoint(section: str, name: str) -> tuple[str, str]:
    """Return (HTTP_METHOD, path_template) for the named command.

    Example:
        method, path = endpoint("github", "create_issue")
        # method="POST", path="/repos/{repo}/issues"

    Raises KeyError with a descriptive message if section or name is missing.
    Raises ValueError if the stored value is malformed (no space separator).
    """
    try:
        raw = _CMDS[section][name]
    except KeyError:
        raise KeyError(f"No command defined for [{section!r}][{name!r}]") from None
    if " " not in raw:
        raise ValueError(f"Malformed command entry [{section!r}][{name!r}]: {raw!r}")
    method, path = raw.split(" ", 1)
    return method, path
