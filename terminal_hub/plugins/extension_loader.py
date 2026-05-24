"""Load and validate extensions from command_config.json."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def load_config(config_path: Path) -> list[dict[str, Any]]:
    """Read and parse command_config.json. Returns list of extension dicts.

    Raises RuntimeError if file is missing or JSON is invalid.
    """
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []  # no config = no extensions, not an error
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to load {config_path}: {exc}") from exc

    if not isinstance(data, dict) or "extensions" not in data:
        raise RuntimeError(f"Invalid command_config.json: missing 'extensions' key")

    return data["extensions"]


def check_deps(ext: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check required CLI tools are available. Returns (ok, missing_list)."""
    missing = [cmd for cmd in ext.get("requires", []) if not shutil.which(cmd)]
    return (len(missing) == 0, missing)


def validate_extension(ext: dict[str, Any]) -> list[str]:
    """Return list of validation errors for an extension dict. Empty = valid."""
    errors = []
    if not ext.get("id"):
        errors.append("missing 'id'")
    if not ext.get("platforms"):
        errors.append("missing 'platforms'")
    if ext.get("fallback") not in (None, "claude", "skip", "abort"):
        errors.append(f"invalid fallback: {ext.get('fallback')!r}")
    return errors


def load_extensions(root: Path) -> list[dict[str, Any]]:
    """Load, validate, and dep-check all extensions. Returns enabled extensions only.

    Searches: root/extensions/command_config.json, then
              root/hub_agents/extensions/command_config.json (project-scoped).
    Warns to stdout for disabled/invalid extensions.
    """
    configs = [
        root / "extensions" / "command_config.json",
        root / "hub_agents" / "extensions" / "command_config.json",
    ]

    enabled = []
    for config_path in configs:
        try:
            exts = load_config(config_path)
        except RuntimeError as exc:
            print(f"⚠ {exc}")
            continue

        for ext in exts:
            # skip comments
            if ext.get("id", "").startswith("_") or "_comment" in ext:
                continue

            errors = validate_extension(ext)
            if errors:
                print(f"⚠ Extension skipped (invalid): {errors}")
                continue

            ok, missing = check_deps(ext)
            if not ok:
                print(f"⚠ Extension '{ext['id']}' disabled — missing: {', '.join(missing)}")
                continue

            enabled.append(ext)

    return enabled
