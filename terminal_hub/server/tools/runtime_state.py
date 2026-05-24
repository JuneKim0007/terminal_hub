"""``get_runtime_state`` — snapshot of what is loaded right now.

Used by ``/terminal_hub:active`` to show every cache, prompt, and loaded
extension at a glance. Aggregates analyzer snapshot age, project docs,
issue counts, and in-memory cache hotness from the github_planner
extension.
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from terminal_hub.config.env_store import read_env
from terminal_hub.config.settings import load_config


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

        items = []

        # Analyzer snapshot
        from extensions.gh_management.github_planner.analyzer import (
            _snapshot_path,
            load_snapshot,
            snapshot_age_hours,
            summarize_for_prompt,
        )
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

        cfg = load_config(root) or {}
        env = read_env(root)

        # In-memory cache status from github_planner extension (#138)
        cache_status: dict[str, str] = {}
        try:
            from extensions.gh_management.github_planner import (
                _ANALYSIS_CACHE,
                _FILE_TREE_CACHE,
                _LABEL_CACHE,
                _MILESTONE_CACHE,
                _PROJECT_DOCS_CACHE,
                _REPO_CACHE,
            )
            cache_status = {
                "analysis_cache":     "🔵 hot" if _ANALYSIS_CACHE else "⚪ empty",
                "project_docs_cache": "🔵 hot" if _PROJECT_DOCS_CACHE else "⚪ empty",
                "file_tree_cache":    "🔵 hot" if _FILE_TREE_CACHE else "⚪ empty",
                "label_cache":        "🔵 hot" if _LABEL_CACHE else "⚪ empty",
                "milestone_cache":    "🔵 hot" if _MILESTONE_CACHE else "⚪ empty",
                "repo_cache":         "🔵 hot" if _REPO_CACHE else "⚪ empty",
            }
        except ImportError:
            pass

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

        ext_lines = []
        for e in _srv._LOADED_EXTENSIONS:
            n_tools = len(e.get("tools", []))
            desc = ""
            mp = e.get("manifest_path", "")
            if mp:
                desc_path = Path(mp).parent / "description.json"
                if desc_path.exists():
                    try:
                        raw = json.loads(desc_path.read_text(encoding="utf-8"))
                        desc = raw.get("summary") or (raw.get("entry") or {}).get("use_when") or ""
                    except Exception:
                        pass
            summary = f" — {desc}" if desc else ""
            ext_lines.append(f"  • {e['name']}{summary} ({n_tools} tools)")

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
        github_repo = env.get("GITHUB_REPO")
        if github_repo:
            repo_line = f"GitHub repo: {github_repo}"
        elif mode == "local":
            repo_line = "Local mode (no GitHub repo connected)"
        else:
            repo_line = "Repo: not configured"
        footer = f"{repo_line}  (mode: {mode})\nRuntime reflects server startup state."
        display = header + "\n" + runtime_block + "\n" + "─" * 50 + "\n" + \
                  caches_block + "\n" + "─" * 50 + "\n" + \
                  (mem_block + "\n" + "─" * 50 + "\n" if mem_block else "") + footer

        return {"items": items, "runtime": runtime, "config": cfg, "_display": display}
