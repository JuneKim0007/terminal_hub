"""terminal-hub install command.

Writes the MCP server entry into ~/.claude.json at the global level
(mcpServers, not per-project). All project-specific state is stored in
hub_agents/ at runtime — no per-project install step needed.
"""
import json
import os
import shutil
import sys
from pathlib import Path

_CLAUDE_JSON = Path.home() / ".claude.json"


# ── Pure functions (testable without I/O) ────────────────────────────────────

def build_mcp_config() -> dict:
    """Build the global MCP server config dict (no project-specific env vars)."""
    return {
        "command": shutil.which("python3") or "python3",
        "args": ["-m", "terminal_hub"],
    }


def read_claude_json(path: Path) -> dict:
    """Read ~/.claude.json, returning {} on missing or invalid JSON."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def write_claude_json(path: Path, config: dict) -> None:
    """Inject the terminal-hub MCP entry into the global mcpServers section."""
    data = read_claude_json(path)
    data.setdefault("mcpServers", {})
    data["mcpServers"]["terminal-hub"] = config
    path.write_text(json.dumps(data, indent=2))


def format_diff(config: dict) -> str:
    """Return a human-readable preview of what will be written."""
    lines = [
        "Will add to ~/.claude.json (global):",
        '  mcpServers["terminal-hub"] = {',
        f'    "command": "{config["command"]}",',
        f'    "args": {config["args"]}',
        "  }",
    ]
    return "\n".join(lines)


_COMMANDS_SRC = Path(__file__).parent.parent / "commands" / "builtin"


def install_commands(claude_dir: Path = Path.home() / ".claude") -> list[str]:
    """Copy builtin .md command files into <claude_dir>/commands/terminal_hub/.

    Returns list of copied filenames.
    Raises PermissionError if claude_dir is not writable.
    """
    if not os.access(claude_dir, os.W_OK):
        raise PermissionError(
            f"Cannot write to {claude_dir} — check directory permissions. "
            f"Run: chmod u+w {claude_dir}"
        )
    commands_dst = claude_dir / "commands" / "terminal_hub"
    commands_dst.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for src_file in sorted(_COMMANDS_SRC.glob("*.md")):
        shutil.copy2(src_file, commands_dst / src_file.name)
        copied.append(src_file.name)
    return copied


def install_plugin_commands(manifest: dict, claude_dir: Path) -> None:
    """Copy plugin commands/*.md to <claude_dir>/commands/<plugin_name>/."""
    plugin_dir = Path(manifest["_plugin_dir"])
    commands_src = plugin_dir / manifest["commands_dir"]
    dest = claude_dir / "commands" / manifest["name"]
    dest.mkdir(parents=True, exist_ok=True)
    for cmd_file in manifest["commands"]:
        src = commands_src / cmd_file
        if src.exists():
            shutil.copy2(src, dest / cmd_file)


def verify_commands(claude_dir: Path = Path.home() / ".claude") -> list[str]:
    """Return list of missing builtin .md filenames in <claude_dir>/commands/terminal_hub/.

    Empty list means all builtin commands are present.
    """
    commands_dst = claude_dir / "commands" / "terminal_hub"
    if not commands_dst.exists():
        return [f.name for f in sorted(_COMMANDS_SRC.glob("*.md"))]
    missing: list[str] = []
    for src_file in sorted(_COMMANDS_SRC.glob("*.md")):
        if not (commands_dst / src_file.name).exists():
            missing.append(src_file.name)
    return missing


# ── Interactive helpers ───────────────────────────────────────────────────────

def _confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


# ── Install ───────────────────────────────────────────────────────────────────

def run_install(claude_json_path: Path = _CLAUDE_JSON, claude_dir: Path = Path.home() / ".claude") -> None:
    """Install terminal-hub globally into ~/.claude.json."""
    print("terminal-hub installer\n")

    config = build_mcp_config()
    print(format_diff(config))
    print()

    if not _confirm("Write this config?"):
        print("Aborted.")
        sys.exit(0)

    write_claude_json(claude_json_path, config)
    print(f"✓ Written to {claude_json_path}")

    try:
        copied = install_commands(claude_dir)
        print(f"✓ Installed {len(copied)} slash command(s) to {claude_dir / 'commands' / 'terminal_hub'}")
    except PermissionError as exc:
        print(f"⚠ Could not install slash commands: {exc}")

    # Install plugin commands
    from terminal_hub.plugin_loader import discover_plugins
    plugins_dir = Path(__file__).parent.parent / "plugins"
    manifests = discover_plugins(plugins_dir)
    for manifest in manifests:
        try:
            install_plugin_commands(manifest, claude_dir)
            print(f"✓ Installed plugin commands for {manifest['name']}")
        except (OSError, PermissionError) as exc:
            print(f"⚠ Could not install plugin commands for {manifest['name']}: {exc}")

    print("\n✓ Restart Claude Code to apply changes.")
    print("  On first use in any project, terminal-hub will ask you to run setup_workspace.")


# ── Verify ────────────────────────────────────────────────────────────────────

def run_verify(claude_json_path: Path = _CLAUDE_JSON, claude_dir: Path = Path.home() / ".claude") -> None:
    """Check whether terminal-hub is configured globally."""
    data = read_claude_json(claude_json_path)
    entry = data.get("mcpServers", {}).get("terminal-hub")

    if entry is None:
        print("✗ terminal-hub is NOT in global mcpServers.")
        print("  Run `terminal-hub install` to set it up.")
        sys.exit(1)

    print("✓ terminal-hub is configured globally.")
    print(json.dumps(entry, indent=2))

    missing = verify_commands(claude_dir)
    if missing:
        print(f"\n⚠ Missing slash command(s): {', '.join(missing)}")
        print("  Run `terminal-hub install` to reinstall.")
    else:
        print("\n✓ All slash commands installed.")
