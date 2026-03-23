"""Plugin discovery and loading for terminal-hub."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

from terminal_hub.namespace import COMMAND_NAMESPACE


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

    Also reads description.json from the same directory if present,
    storing it as manifest['_description'].
    Skips invalid manifests with a stderr warning.
    """
    import sys
    manifests = []
    if not plugins_dir.exists():
        return manifests
    seen: set[Path] = set()
    all_paths = sorted(plugins_dir.glob("*/plugin.json")) + sorted(plugins_dir.glob("*/*/plugin.json"))
    for manifest_path in all_paths:
        if manifest_path in seen:
            continue
        seen.add(manifest_path)
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

        # Load description.json if present — optional, degrades gracefully
        desc_path = manifest_path.parent / "description.json"
        if desc_path.exists():
            try:
                manifest["_description"] = json.loads(desc_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

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
    """Build MCP instructions string from plugin manifests and description.json catalogs.

    Uses install_namespace + entry_command from each manifest to generate the
    correct slash command path. Falls back to plugin name if not present.
    Injects sub-command catalog and triggers from description.json when available.
    """
    lines = [
        "terminal-hub connected.",
        "",
        "BEHAVIOUR RULE: Before writing any code, editing any file, or making any",
        "change to the project, you MUST first draft a GitHub issue with `draft_issue()`",
        "and get explicit user confirmation. Never implement directly — always issue first.",
        "If the user describes a bug, feature, or TODO: draft an issue, show it, and wait",
        "for 'yes' before doing anything. The only exception is if the user explicitly says",
        "\"just do it\" or \"skip the issue\" — then proceed without drafting.",
        "",
        "Available plugins:",
    ]

    for p in plugins:
        namespace = p.get("install_namespace", COMMAND_NAMESPACE)
        entry_cmd = p.get("entry_command", p["commands"][0] if p.get("commands") else "")
        entry_stem = Path(entry_cmd).stem if entry_cmd else p["name"]
        cmd_path = f"/{namespace}:{entry_stem}"

        desc = p.get("_description", {})
        plugin_desc = p.get("description", "")
        lines.append(f"  • {p['name']}: {plugin_desc}")
        lines.append(f"    Start: {cmd_path}")

        # Sub-command catalog from description.json
        subcommands = desc.get("subcommands", [])
        if subcommands:
            lines.append("    Sub-commands:")
            for sc in subcommands[:6]:
                scmd = sc.get("command", "")
                aliases = sc.get("aliases", [])[:2]
                alias_str = f' ("{aliases[0]}")' if aliases else ""
                use_when = sc.get("use_when", "")
                lines.append(f"      {scmd}{alias_str} — {use_when}")

        # Conversation triggers
        triggers = p.get("conversation_triggers", [])
        if triggers:
            trigger_str = ", ".join(f'"{t}"' for t in triggers[:3])
            lines.append(f"    Offer {cmd_path} when user says: {trigger_str}")

    lines.append("")
    lines.append("On first use in a project: call get_setup_status to check initialisation.")
    return "\n".join(lines)
