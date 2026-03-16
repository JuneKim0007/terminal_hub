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
    _MSGS = json.loads(path.read_text())


_load()


def msg(key: str, **kwargs: str) -> str:
    """Return the error message for *key*, formatting in any kwargs."""
    template = _MSGS.get(key, f"Unknown error: {key}")
    return template.format(**kwargs) if kwargs else template
