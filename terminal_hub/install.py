"""terminal-hub install command.

Writes the MCP server entry into ~/.claude.json for the current project,
stores PROJECT_ROOT + GITHUB_REPO in .terminal_hub/.env, and ensures
.terminal_hub/.env is gitignored.
"""
import json
import shutil
import sys
from pathlib import Path

_CLAUDE_JSON = Path.home() / ".claude.json"
_SECURITY_NOTICE = """
\033[33m⚠️  Security notice:\033[0m
   Credentials are stored in .terminal_hub/.env
   This file may contain sensitive tokens — do not share it or commit it to git.
   It has been added to your .gitignore automatically.
"""


# ── Pure functions (testable without I/O) ────────────────────────────────────

def build_mcp_config(root: Path, repo: str | None) -> dict:
    """Build the MCP server config dict for a project."""
    env = {"PROJECT_ROOT": str(root)}
    if repo:
        env["GITHUB_REPO"] = repo
    return {
        "command": shutil.which("python3") or "python3",
        "args": ["-m", "terminal_hub"],
        "env": env,
    }


def read_claude_json(path: Path) -> dict:
    """Read ~/.claude.json, returning {} on missing or invalid JSON."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def write_claude_json(path: Path, root: Path, config: dict) -> None:
    """Inject the terminal-hub MCP entry into ~/.claude.json."""
    data = read_claude_json(path)
    data.setdefault("projects", {})
    data["projects"].setdefault(str(root), {})
    data["projects"][str(root)].setdefault("mcpServers", {})
    data["projects"][str(root)]["mcpServers"]["terminal-hub"] = config
    path.write_text(json.dumps(data, indent=2))


def format_diff(root: Path, config: dict) -> str:
    """Return a human-readable preview of what will be written."""
    lines = [
        f'Will add to ~/.claude.json:',
        f'  projects["{root}"]["mcpServers"]["terminal-hub"] = {{',
        f'    "command": "{config["command"]}",',
        f'    "args": {config["args"]},',
        f'    "env": {json.dumps(config["env"])}',
        f'  }}',
    ]
    return "\n".join(lines)


# ── Interactive install flow ──────────────────────────────────────────────────

def _prompt(msg: str, default: str = "") -> str:
    if default:
        result = input(f"{msg} [{default}]: ").strip()
        return result or default
    return input(f"{msg}: ").strip()


def _confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


def _resolve_root() -> Path:
    from terminal_hub.workspace import resolve_workspace_root, is_valid_project
    root = resolve_workspace_root()
    if root and is_valid_project(root):
        print(f"✓ Detected project directory: {root}")
        return root

    print("Could not auto-detect project directory.")
    while True:
        raw = _prompt("Enter project directory path").strip()
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            return path
        print(f"  ✗ Not a directory: {path}")


def _resolve_repo(root: Path) -> str | None:
    from terminal_hub.workspace import detect_repo
    import os
    repo = os.environ.get("GITHUB_REPO") or detect_repo(root)
    if repo:
        print(f"✓ Detected GitHub repo: {repo}")
        return repo

    raw = _prompt("Enter GitHub repo (owner/repo) or leave blank for local-only mode", "")
    return raw.strip() or None


def run_install(claude_json_path: Path = _CLAUDE_JSON) -> None:
    """Interactive installer. Writes MCP config and .env, then prompts for restart."""
    print("terminal_hub installer\n")

    root = _resolve_root()
    repo = _resolve_repo(root)

    config = build_mcp_config(root, repo)
    print()
    print(format_diff(root, config))
    print()

    if not _confirm("Write this config?"):
        print("Aborted.")
        sys.exit(0)

    write_claude_json(claude_json_path, root, config)
    print(f"✓ Written to {claude_json_path}")

    from terminal_hub.env_store import write_env
    values = {"PROJECT_ROOT": str(root)}
    if repo:
        values["GITHUB_REPO"] = repo
    write_env(root, values)

    print(_SECURITY_NOTICE)
    print("✓ Restart Claude Code to apply changes.")
