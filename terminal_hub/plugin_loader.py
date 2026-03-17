"""Plugin discovery and loading for terminal-hub."""
from __future__ import annotations

import importlib
import json
from pathlib import Path


_REQUIRED_FIELDS = {"name", "version", "entry", "commands_dir", "commands"}


def validate_manifest(manifest: dict) -> list[str]:
    """Return list of validation errors. Empty list = valid."""
    errors = []
    for field in _REQUIRED_FIELDS:
        if field not in manifest:
            errors.append(f"missing required field: {field!r}")
    if "name" in manifest and not manifest["name"].replace("_", "").replace("-", "").isalnum():
        errors.append("name must be alphanumeric (hyphens/underscores allowed)")
    return errors


def discover_plugins(plugins_dir: Path) -> list[dict]:
    """Return validated manifests from plugins/*/plugin.json.
    Skips invalid manifests with a stderr warning."""
    import sys
    manifests = []
    if not plugins_dir.exists():
        return manifests
    for manifest_path in sorted(plugins_dir.glob("*/plugin.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[terminal-hub] warning: could not read {manifest_path}: {exc}", file=sys.stderr)
            continue
        errors = validate_manifest(manifest)
        if errors:
            print(f"[terminal-hub] warning: invalid manifest {manifest_path}: {errors}", file=sys.stderr)
            continue
        manifest["_plugin_dir"] = str(manifest_path.parent)
        manifests.append(manifest)
    return manifests


def load_plugin(manifest: dict, mcp) -> str | None:
    """Import plugin entry module and call register(mcp).
    Returns error string if load fails, None on success."""
    try:
        module = importlib.import_module(manifest["entry"])
        module.register(mcp)
        return None
    except Exception as exc:  # noqa: BLE001
        return f"{manifest['name']}: {type(exc).__name__} — {exc}"


def build_instructions(plugins: list[dict]) -> str:
    """Build MCP instructions string with plugin trigger hints."""
    lines = ["terminal-hub connected. Available plugins:"]
    for p in plugins:
        triggers = p.get("conversation_triggers", [])
        trigger_str = ", ".join(f'"{t}"' for t in triggers[:3])
        desc = p.get("description", "")
        lines.append(f"  • {p['name']}: {desc}")
        if triggers:
            lines.append(f"    Offer to enable if user mentions: {trigger_str}")
    lines.append("")
    lines.append("Type /github_planner:start to begin the GitHub planner.")
    return "\n".join(lines)
