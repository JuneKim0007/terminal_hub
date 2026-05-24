"""Centralized error message loader.

All user-facing error strings live in error_msg.json.
Import msg() and call it with a key + optional format kwargs.
"""
import json
from pathlib import Path

_MSGS: dict[str, str] = {}


def _load() -> None:
    global _MSGS
    path = Path(__file__).parent / "error_msg.json"
    try:
        _MSGS = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to load error_msg.json: {exc}") from exc


_load()


def msg(key: str, **kwargs: str) -> str:
    """Return the error message for *key*, formatting in any kwargs.

    Always calls str.format() so missing placeholders are surfaced as a clear
    developer-facing string rather than silently returning an unformatted template.
    """
    template = _MSGS.get(key, f"Unknown error: {key}")
    try:
        return template.format(**kwargs)
    except KeyError as exc:
        return f"[msg error: missing placeholder {exc} for key {key!r}]"
