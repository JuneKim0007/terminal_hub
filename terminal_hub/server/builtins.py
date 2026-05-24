"""Builtin slash-command files shipped with terminal-hub.

These live under ``extensions/builtin/`` at the project root (next to the
``terminal_hub`` package). The constants and helpers here are the single
source of truth for that path so the rest of the server can stay agnostic
about installation layout.
"""
from __future__ import annotations

from pathlib import Path

# extensions/ sits at the project root, two levels up from this file:
# .../terminal_hub/server/builtins.py → terminal_hub/server → terminal_hub → <root>
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BUILTIN_DIR = _PROJECT_ROOT / "extensions" / "builtin"

_BUILTIN_COMMANDS = ["help.md", "active.md", "converse.md"]


def _load_agent(name: str) -> str:
    """Return the contents of a builtin command file, or '' if missing."""
    path = _BUILTIN_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _assert_builtins() -> None:
    """Raise RuntimeError if any required builtin command file is missing.

    The command list is read from ``terminal_hub.server._BUILTIN_COMMANDS``
    at call time so tests that monkeypatch the package-level attribute
    (``srv._BUILTIN_COMMANDS = [...]``) take effect without re-importing.
    """
    import terminal_hub.server as _srv  # late import → dynamic lookup
    commands = getattr(_srv, "_BUILTIN_COMMANDS", _BUILTIN_COMMANDS)
    missing = [f for f in commands if not (_BUILTIN_DIR / f).exists()]
    if missing:
        raise RuntimeError(f"Missing builtin command files: {missing}")
