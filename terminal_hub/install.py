"""terminal-hub install command.

Writes the MCP server entry into ~/.claude.json at the global level
(mcpServers, not per-project). All project-specific state is stored in
hub_agents/ at runtime — no per-project install step needed.
"""
import json
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


# ── Interactive helpers ───────────────────────────────────────────────────────

def _confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


# ── Install ───────────────────────────────────────────────────────────────────

def run_install(claude_json_path: Path = _CLAUDE_JSON) -> None:
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
    print("\n✓ Restart Claude Code to apply changes.")
    print("  On first use in any project, terminal-hub will ask you to run setup_workspace.")


# ── Verify ────────────────────────────────────────────────────────────────────

def run_verify(claude_json_path: Path = _CLAUDE_JSON) -> None:
    """Check whether terminal-hub is configured globally."""
    data = read_claude_json(claude_json_path)
    entry = data.get("mcpServers", {}).get("terminal-hub")

    if entry is None:
        print("✗ terminal-hub is NOT in global mcpServers.")
        print("  Run `terminal-hub install` to set it up.")
        sys.exit(1)

    print("✓ terminal-hub is configured globally.")
    print(json.dumps(entry, indent=2))
