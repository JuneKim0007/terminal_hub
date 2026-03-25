"""Project documentation helpers — caches, renderers, config, and MCP tool implementations."""
# stdlib
import json
import os
import re
import time
from pathlib import Path


def _pkg():
    """Return the github_planner package module so patches applied by tests are respected."""
    import sys
    return sys.modules['extensions.gh_management.github_planner']

from terminal_hub.constants import SECONDS_PER_HOUR

# ── Cache ─────────────────────────────────────────────────────────────────────
_PROJECT_DOCS_CACHE: dict[str, dict] = {}
# Key: "owner/repo"
# {
#   "summary":    str | None,
#   "detail":     str | None,
#   "_sections":  dict[str, str] | None,  # parsed H2 sections of detail
#   "loaded_at":  float,
# }

# Key: str(workspace_root) — separate entries per project root
_SESSION_HEADER_CACHE: dict[str, dict] = {}


def _gh_planner_docs_dir(root: Path) -> Path:
    return root / "hub_agents" / "extensions" / "gh_planner"


def _docs_config_path(root: Path) -> Path:
    return _gh_planner_docs_dir(root) / "docs_config.json"


def _load_docs_config(root: Path) -> dict:
    path = _docs_config_path(root)
    if not path.exists():
        return {"primary": "hub_agents/project_summary.md", "detail": "hub_agents/project_detail.md", "skills": None, "others": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"primary": "hub_agents/project_summary.md", "detail": "hub_agents/project_detail.md", "skills": None, "others": []}


def _save_docs_config(root: Path, config: dict) -> None:
    from extensions.gh_management.github_planner.storage import _atomic_write
    path = _docs_config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(config, indent=2))


def _resolve_repo(repo: str | None) -> str | None:
    """Return explicit repo or fall back to env / single cached entry."""
    from extensions.gh_management.github_planner.analysis import _ANALYSIS_CACHE
    _p = _pkg()

    if repo:
        return repo
    root = _p.get_workspace_root()
    env = _p.read_env(root)
    env_repo = env.get("GITHUB_REPO")
    if len(_ANALYSIS_CACHE) == 1:
        cached_repo = next(iter(_ANALYSIS_CACHE))
        if env_repo and cached_repo == env_repo:
            return cached_repo
    return env_repo


def _parse_h2_sections(text: str) -> dict[str, str]:
    """Parse markdown text into {heading: content} for every H2 section."""
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+)", line)
        if m:
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = m.group(1).strip()
            current_lines = []
        else:
            if current_heading is not None:
                current_lines.append(line)
    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()
    return sections


def _render_description(title: str, description: str, notes: str = "") -> str:
    lines = [f"# {title}", "", description.strip()]
    if notes:
        lines += ["", f"**Notes:** {notes}"]
    return "\n".join(lines) + "\n"


def _render_architecture(overview: str, components: list[str] | None = None, notes: str = "") -> str:
    lines = ["# Architecture", "", overview.strip()]
    if components:
        lines += ["", "## Components"]
        lines += [f"- {c}" for c in components]
    if notes:
        lines += ["", f"**Notes:** {notes}"]
    return "\n".join(lines) + "\n"


def _render_detail_section(
    feature_name: str,
    overview: str,
    milestone: str | None = None,
    guidelines: list[str] | None = None,
    anti_patterns: list[str] | None = None,
) -> str:
    lines = []
    if milestone:
        lines.append(f"**Milestone:** {milestone}")
        lines.append("")
    lines.append(overview.strip())
    if guidelines:
        lines += ["", "### Guidelines"]
        lines += [f"- {g}" for g in guidelines]
    if anti_patterns:
        lines += ["", "### Anti-patterns"]
        lines += [f"- {a}" for a in anti_patterns]
    return "\n".join(lines)


def _render_summary_section(
    items: list[str] | None = None,
    table_rows: list[dict] | None = None,
) -> str:
    """Render a summary section body from structured inputs."""
    if table_rows:
        if not table_rows:
            return ""
        headers = list(table_rows[0].keys())
        header_row = "| " + " | ".join(headers) + " |"
        sep_row = "| " + " | ".join("---" for _ in headers) + " |"
        data_rows = ["| " + " | ".join(str(row.get(h, "")) for h in headers) + " |" for row in table_rows]
        return "\n".join([header_row, sep_row] + data_rows)
    if items:
        return "\n".join(f"- {item}" for item in items)
    return ""


def _format_reuse_block(files_in_area: list[dict]) -> str:
    """Build ### Available for Reuse markdown from file_index entries."""
    lines = []
    for f in files_in_area:
        path = f.get("path", "")
        exports = f.get("exports", [])
        module_doc = f.get("module_doc", "")
        for export in exports:
            if isinstance(export, str):
                desc = module_doc.split("\n")[0][:80] if module_doc else "—"
                lines.append(f"- `{export}` — `{path}` — {desc}")
            elif isinstance(export, dict):
                name = export.get("name", "")
                sig = export.get("signature", name)
                doc = export.get("doc", export.get("description", "—"))[:80]
                lines.append(f"- `{sig}` — `{path}` — {doc}")
    if not lines:
        return ""
    return "### Available for Reuse\n" + "\n".join(lines[:20])


def _preserve_reuse_block(existing_section: str, new_section: str) -> str:
    """If new_section lacks ### Available for Reuse, inject it from existing."""
    import re as _re
    if "### Available for Reuse" in new_section:
        return new_section
    m = _re.search(r"(### Available for Reuse\n.*?)(?=###|\Z)", existing_section, _re.DOTALL)
    if not m:
        return new_section
    reuse_block = m.group(1).rstrip() + "\n\n"
    if "### Extension Guidelines" in new_section:
        return new_section.replace("### Extension Guidelines", reuse_block + "### Extension Guidelines", 1)
    return new_section + "\n" + reuse_block


def _render_project_summary(
    goal: str,
    tech_stack: list[str],
    notes: str = "",
    design_principles: list[str] | None = None,
) -> str:
    stack_str = " | ".join(tech_stack) if tech_stack else "TBD"
    lines = [
        f"**Tech Stack:** {stack_str}",
        f"**Goal:** {goal}",
    ]
    if notes:
        lines.append(f"**Notes:** {notes}")
    if design_principles:
        lines += ["", "## Design Principles"]
        lines += [f"- {p}" for p in design_principles]
    return "\n".join(lines) + "\n"


def _do_update_project_description(title: str, description: str, notes: str = "") -> dict:
    from terminal_hub.errors import msg
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    content = _render_description(title, description, notes)
    try:
        path = _p.write_doc_file(root, "project_description", content)
        return {"updated": True, "file": str(path.relative_to(root)), "_display": f"✓ Project description saved — {title}"}
    except (OSError, ValueError) as exc:
        return {"error": "write_failed", "message": msg("write_failed", detail=str(exc)), "_hook": None}


def _do_update_architecture(overview: str, components: list[str] | None = None, notes: str = "") -> dict:
    from terminal_hub.errors import msg
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    content = _render_architecture(overview, components, notes)
    try:
        path = _p.write_doc_file(root, "architecture", content)
        return {"updated": True, "file": str(path.relative_to(root)), "_display": "✓ Architecture notes saved"}
    except (OSError, ValueError) as exc:
        return {"error": "write_failed", "message": msg("write_failed", detail=str(exc)), "_hook": None}


def _do_update_project_detail_section(
    feature_name: str,
    overview: str,
    milestone: str | None = None,
    guidelines: list[str] | None = None,
    anti_patterns: list[str] | None = None,
) -> dict:
    """Merge a single H2 section into project_detail.md without rewriting the full file (#65)."""
    content = _render_detail_section(feature_name, overview, milestone, guidelines, anti_patterns)
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    if not feature_name or not feature_name.strip():
        return {"error": "invalid_input", "message": "feature_name must be non-empty"}
    if not content or not content.strip():
        return {"error": "invalid_input", "message": "overview must be non-empty"}

    docs_dir = _gh_planner_docs_dir(root)
    detail_path = docs_dir / "project_detail.md"
    detail_path.parent.mkdir(parents=True, exist_ok=True)

    section_heading = f"## {feature_name.strip()}"
    new_section = f"{section_heading}\n\n{content.strip()}\n"

    if not detail_path.exists():
        tmp = detail_path.with_suffix(".tmp")
        tmp.write_text(new_section, encoding="utf-8")
        import os as _os2; _os2.replace(tmp, detail_path)
        _PROJECT_DOCS_CACHE.pop(str(root), None)
        return {"updated": True, "action": "created", "feature": feature_name,
                "file": str(detail_path.relative_to(root))}

    existing = detail_path.read_text(encoding="utf-8")

    lines = existing.splitlines(keepends=True)
    heading_lower = section_heading.lower()
    start_idx: int | None = None
    end_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip().lower() == heading_lower:
            start_idx = i
        elif start_idx is not None and i > start_idx and line.startswith("## "):
            end_idx = i
            break

    if start_idx is not None:
        before = lines[:start_idx]
        after = lines[end_idx:] if end_idx is not None else []
        existing_section_text = "".join(lines[start_idx:end_idx] if end_idx is not None else lines[start_idx:])
        preserved_section = _preserve_reuse_block(existing_section_text, new_section)
        new_content = "".join(before) + preserved_section + ("" if not after else "\n" + "".join(after))
        action = "replaced"
    else:
        new_content = existing.rstrip() + "\n\n" + new_section
        action = "appended"

    import os as _os3
    tmp = detail_path.with_suffix(".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    _os3.replace(tmp, detail_path)

    _PROJECT_DOCS_CACHE.pop(str(root), None)

    return {"updated": True, "action": action, "feature": feature_name,
            "file": str(detail_path.relative_to(root)),
            "_display": f"✅ **Updated** `project_detail.md` — {feature_name}"}


def _do_update_project_summary_section(
    section_name: str,
    items: list[str] | None = None,
    table_rows: list[dict] | None = None,
) -> dict:
    """Merge a single H2 section into project_summary.md without rewriting the full file (#137)."""
    content = _render_summary_section(items=items, table_rows=table_rows)
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    if not section_name or not section_name.strip():
        return {"error": "invalid_input", "message": "section_name must be non-empty"}
    if not content or not content.strip():
        return {"error": "invalid_input", "message": "items or table_rows must be provided and non-empty"}

    docs_dir = _gh_planner_docs_dir(root)
    summary_path = docs_dir / "project_summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    section_heading = f"## {section_name.strip()}"
    new_section = f"{section_heading}\n\n{content.strip()}\n"

    if not summary_path.exists():
        import os as _os4
        tmp = summary_path.with_suffix(".tmp")
        tmp.write_text(new_section, encoding="utf-8")
        _os4.replace(tmp, summary_path)
        _PROJECT_DOCS_CACHE.pop(str(root), None)
        return {"updated": True, "action": "created", "section": section_name,
                "file": str(summary_path.relative_to(root))}

    existing = summary_path.read_text(encoding="utf-8")
    lines = existing.splitlines(keepends=True)
    heading_lower = section_heading.lower()
    start_idx: int | None = None
    end_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip().lower() == heading_lower:
            start_idx = i
        elif start_idx is not None and i > start_idx and line.startswith("## "):
            end_idx = i
            break

    if start_idx is not None:
        before = lines[:start_idx]
        after = lines[end_idx:] if end_idx is not None else []
        new_content = "".join(before) + new_section + ("" if not after else "\n" + "".join(after))
        action = "replaced"
    else:
        new_content = existing.rstrip() + "\n\n" + new_section
        action = "appended"

    import os as _os5
    tmp = summary_path.with_suffix(".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    _os5.replace(tmp, summary_path)
    _PROJECT_DOCS_CACHE.pop(str(root), None)

    return {"updated": True, "action": action, "section": section_name,
            "file": str(summary_path.relative_to(root)),
            "_display": f"✅ **Updated** `project_summary.md` — {section_name}"}


def _do_get_project_context(doc_key: str) -> dict:
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    if doc_key == "all":
        loaded = _do_load_project_docs(doc="all")
        return {
            "project_description": loaded.get("summary"),
            "architecture": loaded.get("detail"),
        }
    _KEY_MAP = {"project_description": "summary", "architecture": "detail",
                "summary": "summary", "detail": "detail"}
    mapped = _KEY_MAP.get(doc_key)
    if mapped is None:
        return {"error": "not_found", "message": f"Unknown doc key: {doc_key!r}", "_hook": None}
    loaded = _do_load_project_docs(doc=mapped)
    content = loaded.get(mapped)
    return {"doc_key": doc_key, "content": content}


def _do_save_project_docs(
    goal: str,
    tech_stack: list[str],
    notes: str = "",
    design_principles: list[str] | None = None,
    repo: str | None = None,
) -> dict:
    from extensions.gh_management.github_planner.analysis import _ANALYSIS_CACHE
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    summary_md = _render_project_summary(goal, tech_stack, notes, design_principles)

    docs_dir = _gh_planner_docs_dir(root)
    docs_dir.mkdir(parents=True, exist_ok=True)

    dest = docs_dir / "project_summary.md"
    tmp = dest.with_suffix(".tmp")
    try:
        tmp.write_text(summary_md, encoding="utf-8")
        os.replace(tmp, dest)
    except OSError as exc:
        return {"error": "write_failed", "message": str(exc), "_hook": None}

    detail_dest = docs_dir / "project_detail.md"
    if not detail_dest.exists():
        detail_dest.write_text("", encoding="utf-8")

    resolved = _resolve_repo(repo) or "unknown"
    _PROJECT_DOCS_CACHE[resolved] = {
        "summary": summary_md,
        "detail": "",
        "_sections": {},
        "loaded_at": time.time(),
    }
    _ANALYSIS_CACHE.pop(resolved, None)
    _SESSION_HEADER_CACHE.pop(str(root), None)

    stack_display = ", ".join(tech_stack[:3]) + ("…" if len(tech_stack) > 3 else "")
    return {
        "saved": True,
        "summary_path": str((docs_dir / "project_summary.md").relative_to(root)),
        "_display": f"✓ Project docs saved — {goal[:60]} [{stack_display}]",
    }


def _do_load_project_docs(doc: str = "summary", repo: str | None = None, force_reload: bool = False) -> dict:
    resolved = _resolve_repo(repo) or "unknown"
    cached = _PROJECT_DOCS_CACHE.get(resolved)

    root = _pkg().get_workspace_root()
    docs_dir = _gh_planner_docs_dir(root)

    def _file_size(name: str) -> str:
        p = docs_dir / name
        return f"{p.stat().st_size:,} bytes" if p.exists() else "missing"

    if cached and not force_reload:
        if doc == "summary":
            return {"summary": cached.get("summary"), "detail": None,
                    "_display": f"📄 Loaded: project_summary.md ({_file_size('project_summary.md')}) [cached]"}
        if doc == "detail":
            return {"summary": None, "detail": cached.get("detail"),
                    "_display": f"📄 Loaded: project_detail.md ({_file_size('project_detail.md')}) [cached]"}
        return {"summary": cached.get("summary"), "detail": cached.get("detail"),
                "_display": (f"📄 Loaded: project_summary.md ({_file_size('project_summary.md')}), "
                             f"project_detail.md ({_file_size('project_detail.md')}) [cached]")}

    def _read(name: str) -> str | None:
        p = docs_dir / name
        return p.read_text(encoding="utf-8") if p.exists() else None

    summary = _read("project_summary.md")
    detail = _read("project_detail.md")

    entry: dict = {"summary": summary, "detail": detail, "loaded_at": time.time()}

    if detail is not None:
        detail_path = docs_dir / "project_detail.md"
        if detail_path.exists():
            entry["_sections"] = _parse_h2_sections(detail)
            entry["_sections_mtime"] = detail_path.stat().st_mtime

    _PROJECT_DOCS_CACHE[resolved] = entry

    result: dict = {}
    display_parts: list[str] = []
    if doc in ("summary", "all"):
        result["summary"] = summary
        display_parts.append(f"project_summary.md ({_file_size('project_summary.md')})")
    if doc in ("detail", "all"):
        result["detail"] = detail
        display_parts.append(f"project_detail.md ({_file_size('project_detail.md')})")
    if doc == "summary":
        result["detail"] = None
    elif doc == "detail":
        result["summary"] = None

    display = "📄 Loaded: " + ", ".join(display_parts) if display_parts else "📄 Loaded: (nothing)"
    result["_display"] = display
    return result


def _do_docs_exist(repo: str | None = None) -> dict:
    root = _pkg().get_workspace_root()
    docs_dir = _gh_planner_docs_dir(root)
    summary_path = docs_dir / "project_summary.md"
    detail_path = docs_dir / "project_detail.md"

    summary_exists = summary_path.exists()
    detail_exists = detail_path.exists()
    age_hours: float | None = None
    if summary_exists:
        age_hours = (time.time() - summary_path.stat().st_mtime) / SECONDS_PER_HOUR

    sections: list[str] = []
    if detail_exists:
        resolved = _resolve_repo(repo) or "unknown"
        entry = _PROJECT_DOCS_CACHE.setdefault(resolved, {})
        current_mtime = detail_path.stat().st_mtime
        cached_mtime: float | None = entry.get("_sections_mtime")
        cached_sections: dict[str, str] | None = entry.get("_sections")
        if cached_sections is None or cached_mtime != current_mtime:
            cached_sections = _parse_h2_sections(detail_path.read_text(encoding="utf-8"))
            entry["_sections"] = cached_sections
            entry["_sections_mtime"] = current_mtime
        sections = list(cached_sections.keys())
        if entry.get("summary") is None and summary_exists:
            entry["summary"] = summary_path.read_text(encoding="utf-8")

    return {
        "summary_exists": summary_exists,
        "detail_exists": detail_exists,
        "summary_age_hours": age_hours,
        "sections": sections,
    }


def _do_lookup_feature_section(feature: str, repo: str | None = None) -> dict:
    """Return the project_detail.md section whose H2 heading best matches `feature`."""
    resolved = _resolve_repo(repo) or "unknown"
    entry = _PROJECT_DOCS_CACHE.setdefault(resolved, {})

    root = _pkg().get_workspace_root()
    docs_dir = _gh_planner_docs_dir(root)
    detail_path = docs_dir / "project_detail.md"
    cached_sections: dict[str, str] | None = entry.get("_sections")

    if not detail_path.exists():
        if cached_sections is not None:
            sections = cached_sections
        else:
            return {
                "matched": False,
                "available_features": [],
                "reason": "project_detail.md not found — run analyze or save_project_docs first",
            }
    else:
        current_mtime = detail_path.stat().st_mtime
        cached_mtime: float | None = entry.get("_sections_mtime")
        if cached_sections is None or cached_mtime != current_mtime:
            cached_sections = _parse_h2_sections(detail_path.read_text(encoding="utf-8"))
            entry["_sections"] = cached_sections
            entry["_sections_mtime"] = current_mtime
        sections = cached_sections

    available = list(sections.keys())
    feature_lower = feature.lower()

    matched_key: str | None = None
    for k in sections:
        if k.lower() == feature_lower:
            matched_key = k
            break
    if matched_key is None:
        for k in sections:
            if feature_lower in k.lower() or k.lower() in feature_lower:
                matched_key = k
                break
    if matched_key is None:
        first_word = feature_lower.split()[0] if feature_lower.split() else ""
        for k in sections:
            if first_word and k.lower().startswith(first_word):
                matched_key = k
                break

    global_rules: str | None = entry.get("summary")
    if global_rules is None:
        root = _pkg().get_workspace_root()
        sp = _gh_planner_docs_dir(root) / "project_summary.md"
        if sp.exists():
            global_rules = sp.read_text(encoding="utf-8")
            entry["summary"] = global_rules

    if matched_key is None:
        return {
            "matched": False,
            "available_features": available,
            "global_rules": global_rules,
        }

    return {
        "matched": True,
        "feature": matched_key,
        "section": sections[matched_key],
        "global_rules": global_rules,
        "available_features": available,
    }


def _do_get_session_header() -> dict:
    """Return a ≤120-token context blob for session start. Cached after first call."""
    root = _pkg().get_workspace_root()
    root_key = str(root)
    if root_key in _SESSION_HEADER_CACHE:
        return _SESSION_HEADER_CACHE[root_key]

    docs_dir = _gh_planner_docs_dir(root)
    summary_path = docs_dir / "project_summary.md"
    detail_path = docs_dir / "project_detail.md"

    if not summary_path.exists():
        result: dict = {"docs": False}
        _SESSION_HEADER_CACHE[root_key] = result
        return result

    age_h = (time.time() - summary_path.stat().st_mtime) / SECONDS_PER_HOUR
    text = summary_path.read_text(encoding="utf-8")
    _goal_m = re.search(r"\*\*Goal:\*\*\s*(.+)", text)
    first_line = _goal_m.group(1).strip() if _goal_m else text.splitlines()[0].lstrip("# ").strip()

    _MAX_SECTIONS_IN_HEADER = 10
    sections: list[str] = []
    total_sections = 0
    if detail_path.exists():
        all_sections = list(_parse_h2_sections(detail_path.read_text(encoding="utf-8")).keys())
        total_sections = len(all_sections)
        sections = all_sections[:_MAX_SECTIONS_IN_HEADER]

    result = {
        "docs": True,
        "age_hours": round(age_h, 1),
        "title": first_line,
        "stale": age_h > 168,
        "sections": sections,
    }
    if total_sections > _MAX_SECTIONS_IN_HEADER:
        result["sections_truncated"] = True
        result["total_sections"] = total_sections
    _SESSION_HEADER_CACHE[root_key] = result
    return result
