"""MCP server for terminal-hub.

Registers core workspace tools and delegates GitHub-specific tools to the
github_planner plugin. Entry point is create_server(), which returns a
configured FastMCP instance ready to call server.run().
"""
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from terminal_hub.config import WorkspaceMode, load_config, save_config
from terminal_hub.env_store import read_env, write_env
from extensions.github_planner.client import load_default_labels
from terminal_hub.workspace import init_workspace, resolve_workspace_root
from terminal_hub.plugin_loader import discover_plugins, load_plugin, build_instructions

# Re-export plugin helpers so tests can patch at terminal_hub.server.*
from extensions.github_planner import (
    get_workspace_root,
    get_github_client,
    ensure_initialized,
    resolve_token,
    verify_gh_cli_auth,
    _invalidate_repo_cache,
)
from extensions.github_planner.storage import (
    write_issue_file,
    write_doc_file,
)

_BUILTIN_DIR = Path(__file__).parent.parent / "extensions" / "builtin"

_BUILTIN_COMMANDS = ["help.md", "active.md", "conversation.md", "converse.md"]

_PLUGIN_WARNINGS: list[str] = []
# Populated during plugin load — each entry: {name, tools: [str], manifest_path}
_LOADED_EXTENSIONS: list[dict] = []


def _load_agent(name: str) -> str:
    path = _BUILTIN_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _assert_builtins() -> None:
    base = Path(__file__).parent.parent / "extensions" / "builtin"
    missing = [f for f in _BUILTIN_COMMANDS if not (base / f).exists()]
    if missing:
        raise RuntimeError(f"Missing builtin command files: {missing}")


_assert_builtins()


def create_server() -> FastMCP:
    """Create and return the configured FastMCP instance."""
    global _PLUGIN_WARNINGS
    _PLUGIN_WARNINGS = []

    plugins_dir = Path(__file__).parent.parent / "extensions"
    loaded_manifests = discover_plugins(plugins_dir)

    instructions = build_instructions(loaded_manifests)
    mcp = FastMCP("terminal-hub", instructions=instructions)

    # ── Core resources ────────────────────────────────────────────────────────

    @mcp.resource("terminal-hub://instructions")
    def instructions_resource() -> str:
        """Full entry point instructions and tool reference."""
        return _load_agent("help.md")

    # ── Workspace setup tools ─────────────────────────────────────────────────

    @mcp.tool()
    def get_setup_status() -> dict:
        """Check if this project has been initialised. Always call this first."""
        root = get_workspace_root()
        hub_dir = root / "hub_agents"
        _G_INIT = "terminal-hub://workflow/init"
        if not hub_dir.exists():
            return {
                "initialised": False,
                "message": (
                    "hub_agents/ not found. "
                    "Ask the user if they want GitHub integration and call setup_workspace."
                ),
                "_guidance": _G_INIT,
            }
        cfg = load_config(root)
        env = read_env(root)
        result: dict = {
            "initialised": True,
            "mode": cfg["mode"] if cfg else "unknown",
            "github_repo": env.get("GITHUB_REPO"),
        }
        if _PLUGIN_WARNINGS:
            result["plugin_warnings"] = _PLUGIN_WARNINGS
        return result

    @mcp.tool()
    def setup_workspace(github_repo: str | None = None) -> dict:
        """Initialise terminal-hub for this project.

        Creates hub_agents/, stores github_repo in hub_agents/.env if provided,
        and gitignores hub_agents/.

        github_repo: optional 'owner/repo' — omit for local-only mode."""
        root = get_workspace_root()

        init_workspace(root)

        from terminal_hub.env_store import _ensure_gitignored
        _ensure_gitignored(root)

        values: dict[str, str] = {}
        if github_repo:
            values["GITHUB_REPO"] = github_repo
        if values:
            write_env(root, values)

        mode = WorkspaceMode.GITHUB if github_repo else WorkspaceMode.LOCAL
        save_config(root, mode, github_repo)
        _invalidate_repo_cache()  # new repo configured — flush cached detect_repo result

        label_warning: str | None = None
        if github_repo:
            gh, _ = get_github_client()
            if gh is not None:
                all_names = [d["name"] for d in load_default_labels()]
                with gh:
                    label_warning = gh.ensure_labels(all_names)

        repo = github_repo or "none"
        result: dict = {
            "success": True,
            "github_repo": github_repo,
            "hub_dir": str(root / "hub_agents"),
            "message": (
                f"Initialised hub_agents/ in {root}. "
                + (f"GitHub repo set to {github_repo}." if github_repo else "Running in local-only mode.")
            ),
            "_display": f"✓ Workspace initialised (mode: {mode.value}, repo: {repo})",
        }
        if label_warning:
            result["label_warning"] = label_warning
        return result

    # ── Session state / runtime state tools ──────────────────────────────────

    @mcp.tool()
    def get_runtime_state() -> dict:
        """Return runtime state (loaded extensions + registered tools) and disk cache state.
        Used by /terminal_hub:active to show what is currently active (#46)."""
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err

        items = []

        # Analyzer snapshot
        from extensions.github_planner.analyzer import _snapshot_path, load_snapshot, snapshot_age_hours, summarize_for_prompt
        snap_path = _snapshot_path(root)
        if snap_path.exists():
            snap = load_snapshot(root)
            age = snapshot_age_hours(snap) if snap else None
            summary = summarize_for_prompt(snap) if snap else None
            items.append({
                "key": "analyzer_snapshot", "label": "Analyzer snapshot", "type": "cache",
                "status": "present", "path": str(snap_path.relative_to(root)),
                "size_bytes": snap_path.stat().st_size,
                "age_hours": round(age, 1) if age is not None else None,
                "summary": summary,
            })
        else:
            items.append({
                "key": "analyzer_snapshot", "label": "Analyzer snapshot", "type": "cache",
                "status": "absent", "path": str(snap_path.relative_to(root)),
                "size_bytes": None, "age_hours": None, "summary": None,
            })

        # Project docs (namespaced under extensions/gh_planner/)
        gh_docs = root / "hub_agents" / "extensions" / "gh_planner"
        for key, label, path in [
            ("project_summary", "Project summary", "hub_agents/extensions/gh_planner/project_summary.md"),
            ("project_detail", "Project detail", "hub_agents/extensions/gh_planner/project_detail.md"),
        ]:
            p = root / path
            items.append({
                "key": key, "label": label, "type": "prompt",
                "status": "present" if p.exists() else "absent",
                "path": path,
                "size_bytes": p.stat().st_size if p.exists() else None,
                "age_hours": None, "summary": None,
            })

        # Issues summary
        issues_dir = root / "hub_agents" / "issues"
        issue_files = list(issues_dir.glob("*.md")) if issues_dir.exists() else []
        pending = sum(1 for f in issue_files if "pending" in f.read_text(encoding="utf-8", errors="ignore"))
        open_count = len(issue_files) - pending
        items.append({
            "key": "issues", "label": "Tracked issues", "type": "cache",
            "status": "present" if issue_files else "absent",
            "path": "hub_agents/issues/",
            "size_bytes": None, "age_hours": None,
            "summary": f"{len(issue_files)} total · {pending} pending · {open_count} open" if issue_files else None,
        })

        # Build _display
        rows = []
        for item in items:
            icon = "✓" if item["status"] == "present" else "✗"
            detail = ""
            if item["status"] == "present":
                if item["age_hours"] is not None:
                    detail = f"  {item['age_hours']}h old"
                elif item["size_bytes"] is not None:
                    detail = f"  {item['size_bytes']} bytes"
                if item["summary"]:
                    detail += f"  {item['summary']}"
            rows.append(f"[{item['type']:<6}] {item['label']:<25} {icon}{detail}")

        cfg = load_config(root) or {}
        env = read_env(root)

        # Build runtime section
        try:
            registered_tools = [t.name for t in mcp._tool_manager.list_tools()]
        except Exception:
            registered_tools = []

        runtime = {
            "loaded_extensions": _LOADED_EXTENSIONS,
            "registered_tools": registered_tools,
            "load_warnings": _PLUGIN_WARNINGS,
        }

        # Build _display
        rows = []
        for item in items:
            icon = "✓" if item["status"] == "present" else "✗"
            detail = ""
            if item["status"] == "present":
                if item["age_hours"] is not None:
                    detail = f"  {item['age_hours']}h old"
                elif item["size_bytes"] is not None:
                    detail = f"  {item['size_bytes']} bytes"
                if item["summary"]:
                    detail += f"  {item['summary']}"
            rows.append(f"[{item['type']:<6}] {item['label']:<25} {icon}{detail}")

        ext_lines = [f"  • {e['name']} ({len(e.get('tools', []))} tools)" for e in _LOADED_EXTENSIONS]
        tool_count = len(registered_tools)
        warn_lines = [f"  ⚠ {w}" for w in _PLUGIN_WARNINGS]

        header = "terminal-hub active state\n" + "─" * 50
        runtime_block = "RUNTIME\n" + ("\n".join(ext_lines) or "  (no extensions loaded)") + \
                        f"\n  {tool_count} tools registered" + \
                        ("\n" + "\n".join(warn_lines) if warn_lines else "")
        caches_block = "CACHES\n" + "\n".join(rows)
        footer = f"Repo: {env.get('GITHUB_REPO', 'not set')}  Mode: {cfg.get('mode', 'unknown')}" + \
                 "\nRuntime reflects server startup state."
        display = header + "\n" + runtime_block + "\n" + "─" * 50 + "\n" + \
                  caches_block + "\n" + "─" * 50 + "\n" + footer

        return {"items": items, "runtime": runtime, "config": cfg, "_display": display}

    # ── Plugin registry tools (#44 / #45) ────────────────────────────────────

    @mcp.tool()
    def scan_plugins() -> dict:
        """Scan extensions/ for description.json files and build hub_agents/plugin.config.json (#44).

        Reads each extension's description.json (name, display_name, usage, commands, triggers).
        Writes a compact registry to hub_agents/plugin.config.json.
        Returns {plugins: [...], unidentified: N, total: N, _display: ...}.
        Use load_plugin_registry() to read the result without re-scanning.
        """
        import json as _json
        import time as _time

        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err

        extensions_dir = Path(__file__).parent.parent / "extensions"
        plugins: list[dict] = []
        unidentified: list[str] = []

        for desc_path in sorted(extensions_dir.rglob("description.json")):
            try:
                raw = _json.loads(desc_path.read_text(encoding="utf-8"))
            except (OSError, _json.JSONDecodeError):
                continue

            # Normalize to registry format — tolerate both old and new schema
            name = raw.get("plugin") or raw.get("name") or desc_path.parent.name
            display_name = raw.get("display_name") or name.replace("_", " ").title()
            usage = (
                raw.get("usage")
                or raw.get("summary")
                or (raw.get("entry") or {}).get("use_when")
                or ""
            )
            path = str(desc_path.parent.relative_to(extensions_dir.parent))

            # Commands: new-schema list or old-schema entry + subcommands
            commands: list[str] = raw.get("commands", [])
            if not commands:
                if entry := raw.get("entry"):
                    if cmd := entry.get("command"):
                        commands = [cmd]
                    for sub in raw.get("subcommands", []):
                        if cmd := sub.get("command"):
                            commands.append(cmd)

            # Triggers: new-schema list or old-schema entry.triggers
            triggers: list[str] = raw.get("triggers", [])
            if not triggers:
                if entry := raw.get("entry"):
                    triggers = entry.get("triggers", [])

            if not usage:
                unidentified.append(name)

            plugins.append({
                "name": name,
                "display_name": display_name,
                "path": path,
                "usage": usage,
                "commands": commands,
                "triggers": triggers,
                "has_description": bool(usage),
            })

        registry = {
            "last_scanned": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "plugins": plugins,
            "unidentified": unidentified,
        }

        config_path = root / "hub_agents" / "plugin.config.json"
        tmp = config_path.with_suffix(".tmp")
        tmp.write_text(_json.dumps(registry, indent=2), encoding="utf-8")
        import os as _os_scan; _os_scan.replace(tmp, config_path)

        n = len(plugins)
        n_unid = len(unidentified)
        return {
            "plugins": plugins,
            "total": n,
            "unidentified": n_unid,
            "_display": (
                f"✓ Scanned {n} plugin(s), {n_unid} missing usage description\n"
                f"  Saved to hub_agents/plugin.config.json"
            ),
        }

    @mcp.tool()
    def load_plugin_registry() -> dict:
        """Load hub_agents/plugin.config.json for plugin matching (#44 / #45).

        Returns {plugins, unidentified, last_scanned} or suggests calling scan_plugins first.
        Each plugin entry: {name, display_name, usage, commands, triggers}.
        """
        import json as _json

        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err

        config_path = root / "hub_agents" / "plugin.config.json"
        if not config_path.exists():
            return {
                "plugins": [],
                "last_scanned": None,
                "_suggest_scan": (
                    "No plugin registry found. Call scan_plugins() to build it — "
                    "enables smart plugin suggestions via /th:converse."
                ),
            }

        try:
            data = _json.loads(config_path.read_text(encoding="utf-8"))
        except (_json.JSONDecodeError, OSError):
            return {"plugins": [], "last_scanned": None, "error": "registry_corrupt"}

        return {
            "plugins": data.get("plugins", []),
            "unidentified": len(data.get("unidentified", [])),
            "last_scanned": data.get("last_scanned"),
        }

    # ── Dynamic plugin loading ────────────────────────────────────────────────

    global _LOADED_EXTENSIONS
    _LOADED_EXTENSIONS = []
    tools_before = {t.name for t in mcp._tool_manager.list_tools()} if hasattr(mcp, "_tool_manager") else set()

    for manifest in loaded_manifests:
        err = load_plugin(manifest, mcp)
        if err:
            _PLUGIN_WARNINGS.append(err)
        else:
            tools_after = {t.name for t in mcp._tool_manager.list_tools()} if hasattr(mcp, "_tool_manager") else set()
            new_tools = sorted(tools_after - tools_before)
            _LOADED_EXTENSIONS.append({
                "name": manifest.get("name", "unknown"),
                "tools": new_tools,
                "manifest_path": str(manifest.get("_path", "")),
            })
            tools_before = tools_after

    return mcp
