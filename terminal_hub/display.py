"""Central display string registry for terminal-hub.

Provides display(key, **kwargs) — the single source of truth for all static
_display strings. Templates live in predefined_text.json; this module reads,
caches, and formats them.

Key format: "feature.action"  e.g. "gh_plan.bootstrap_ready"
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CACHE: dict[str, Any] | None = None
_JSON_PATH = Path(__file__).parent / "predefined_text.json"


def _load() -> dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        _CACHE = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
    return _CACHE


def display(key: str, **kwargs: Any) -> str:
    """Look up a predefined display string and format it with kwargs.

    key format: "feature.action"  e.g. "gh_plan.bootstrap_ready"

    Returns the formatted string ready for use as a _display value.
    Raises KeyError with a descriptive message if the key is not found or
    if a required format variable is missing from kwargs.

    Example:
        display("gh_plan.bootstrap_ready", issue_count=5, milestone_count=2)
        → "✅ **gh-plan ready** — 5 issues, 2 milestones"
    """
    data = _load()
    parts = key.split(".", 1)
    if len(parts) != 2:
        raise KeyError(
            f"display() key must be 'feature.action', got: {key!r}. "
            f"Available features: {list(data)}"
        )
    feature, action = parts
    if feature not in data:
        raise KeyError(
            f"Unknown feature {feature!r} in predefined_text.json. "
            f"Available features: {list(data)}"
        )
    section = data[feature]
    if not isinstance(section, dict) or action not in section:
        raise KeyError(
            f"Unknown action {action!r} under feature {feature!r}. "
            f"Available actions: {list(section) if isinstance(section, dict) else '(not a dict)'}"
        )
    template = section[action]
    if not isinstance(template, str):
        raise KeyError(
            f"predefined_text.json entry {key!r} is not a string template "
            f"(got {type(template).__name__!r}). "
            f"Use display.load_data() for non-string entries."
        )
    try:
        return template.format(**kwargs)
    except KeyError as exc:
        raise KeyError(
            f"Missing format variable {exc} for template {key!r}.\n"
            f"  Template: {template!r}\n"
            f"  Provided: {list(kwargs)}"
        ) from exc


def load_data(key: str) -> Any:
    """Return the raw JSON value for a key (may be dict, list, or str).

    Use this for non-string entries like prompt_coloring.styles.
    key format: "feature.action"
    """
    data = _load()
    parts = key.split(".", 1)
    if len(parts) != 2:
        raise KeyError(f"load_data() key must be 'feature.action', got: {key!r}")
    feature, action = parts
    if feature not in data:
        raise KeyError(f"Unknown feature {feature!r} in predefined_text.json.")
    section = data[feature]
    if not isinstance(section, dict) or action not in section:
        raise KeyError(f"Unknown action {action!r} under feature {feature!r}.")
    return section[action]
