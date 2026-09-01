"""``get_runtime_state`` — snapshot of what is loaded right now.

Used by ``/terminal_hub:active`` to show every cache, prompt, and loaded
extension at a glance. Aggregates analyzer snapshot age, project docs,
issue counts, and in-memory cache hotness from the github_planner
extension.
"""
from __future__ import annotations


from mcp.server.fastmcp import FastMCP

from terminal_hub.plugins import hooks
from terminal_hub.plugins.plugin_loader import extension_summary

from terminal_hub.config.env_store import read_env
from terminal_hub.config.settings import load_config


def _repo_line(github_repo: str | None, mode: str) -> str:
    """The footer line naming the connected repo, or why there is none."""
    if github_repo:
        return f"GitHub repo: {github_repo}"
    if mode == "local":
        return "Local mode (no GitHub repo connected)"
    return "Repo: not configured"


def _item_row(item: dict) -> str:
    """One '[type] label ✓/✗ detail' line of the CACHES block."""
    icon = "✓" if item["status"] == "present" else "✗"
    detail = ""
    if item["status"] == "present":
        if item["age_hours"] is not None:
            detail = f"  {item['age_hours']}h old"
        elif item["size_bytes"] is not None:
            detail = f"  {item['size_bytes']} bytes"
        if item["summary"]:
            detail += f"  {item['summary']}"
    return f"[{item['type']:<6}] {item['label']:<25} {icon}{detail}"


def _disk_state_items(root) -> list[dict]:
    """Presence, size and age of every on-disk artefact the hub tracks."""
    items: list[dict] = []

    # Plugins contribute the artefacts they own (R26).
    for _plugin, rows in hooks.call_all(hooks.DISK_STATE_ITEMS, root):
        items.extend(rows or [])

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
    return items


def register(mcp: FastMCP) -> None:
    """Attach get_runtime_state to *mcp*."""
    import terminal_hub.server as _srv

    @mcp.tool()
    def get_runtime_state() -> dict:
        """Return runtime state (loaded extensions + registered tools) and disk cache state.
        Used by /terminal_hub:active to show what is currently active (#46)."""
        root = _srv.get_workspace_root()
        if err := _srv.ensure_initialized(root):
            return err

        items = _disk_state_items(root)

        cfg = load_config(root) or {}
        env = read_env(root)

        # In-memory cache status from github_planner extension (#138)
        # Plugins report their own caches; the host holds none of its own.
        cache_status: dict[str, str] = {}
        for _plugin, statuses in hooks.call_all(hooks.CACHE_STATUS):
            cache_status.update(statuses or {})

        # Build runtime section
        try:
            registered_tools = [t.name for t in mcp._tool_manager.list_tools()]
        except Exception:
            registered_tools = []

        runtime = {
            "loaded_extensions": list(_srv._LOADED_EXTENSIONS),
            "registered_tools": registered_tools,
            "load_warnings": list(_srv._PLUGIN_WARNINGS),
            "cache_status": cache_status,
        }

        # Build _display
        rows = [_item_row(item) for item in items]

        ext_lines = []
        for e in _srv._LOADED_EXTENSIONS:
            desc = extension_summary(e.get("manifest_path", ""))
            summary = f" — {desc}" if desc else ""
            ext_lines.append(f"  • {e['name']}{summary} ({len(e.get('tools', []))} tools)")

        tool_count = len(registered_tools)
        warn_lines = [f"  ⚠ {w}" for w in _srv._PLUGIN_WARNINGS]

        header = "terminal-hub active state\n" + "─" * 50
        runtime_block = "RUNTIME\n" + ("\n".join(ext_lines) or "  (no extensions loaded)") + \
                        f"\n  {tool_count} tools total — full function awareness active" + \
                        ("\n" + "\n".join(warn_lines) if warn_lines else "")
        caches_block = "CACHES\n" + "\n".join(rows)

        # In-memory cache snapshot (#138)
        if cache_status:
            mem_lines = [f"  {k:<22} {v}" for k, v in cache_status.items()]
            mem_block = "IN-MEMORY CACHES\n" + "\n".join(mem_lines)
        else:
            mem_block = ""
        mode = cfg.get("mode", "unknown")
        repo_line = _repo_line(env.get("GITHUB_REPO"), mode)
        footer = f"{repo_line}  (mode: {mode})\nRuntime reflects server startup state."
        display = header + "\n" + runtime_block + "\n" + "─" * 50 + "\n" + \
                  caches_block + "\n" + "─" * 50 + "\n" + \
                  (mem_block + "\n" + "─" * 50 + "\n" if mem_block else "") + footer

        return {"items": items, "runtime": runtime, "config": cfg, "_display": display}
