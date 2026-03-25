"""Milestone management — caches, label helpers, knowledge files, and MCP tool implementations."""
# stdlib
import json
import re
from pathlib import Path


def _pkg():
    """Return the github_planner package module so patches applied by tests are respected."""
    import sys
    return sys.modules['extensions.gh_management.github_planner']

# ── Constants ─────────────────────────────────────────────────────────────────
_MILESTONE_CACHE: dict[str, list[dict]] = {}  # repo -> [{number, title, description}]

_MILESTONE_LABEL_PALETTE = [
    "0075ca",  # blue
    "e4e669",  # yellow
    "d93f0b",  # orange-red
    "0e8a16",  # green
    "5319e7",  # purple
    "f9d0c4",  # pink
    "c5def5",  # light blue
    "bfd4f2",  # periwinkle
]

_PLUGIN_DIR = Path(__file__).parent


def _milestone_label_color(number: int) -> str:
    """Return a hex color (no #) for milestone label m{number}, cycling through the palette."""
    return _MILESTONE_LABEL_PALETTE[(number - 1) % len(_MILESTONE_LABEL_PALETTE)]


def _ensure_milestone_label(number: int, title: str) -> None:
    """Idempotently create or update the m{N} label on GitHub and sync labels.json."""
    from extensions.gh_management.github_planner.labels import _LABEL_CACHE, _LABEL_ANALYSIS_CACHE
    _p = _pkg()

    root = _p.get_workspace_root()
    label_name = f"m{number}"
    color = _milestone_label_color(number)
    description = title

    gh, err = _p.get_github_client()
    if gh is None:
        return
    repo = _p.read_env(root).get("GITHUB_REPO", "")
    try:
        with gh:
            existing_labels = gh.get_labels()
            if label_name in existing_labels:
                gh.update_label(label_name, description)
            else:
                gh.create_label(label_name, color, description)
        _LABEL_CACHE.pop(repo, None)
        _LABEL_ANALYSIS_CACHE.pop(repo, None)
    except Exception:
        pass  # best-effort

    labels_file = _p._PLUGIN_DIR / "labels.json"
    try:
        existing: list[dict] = json.loads(labels_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = []

    entry = {"name": label_name, "color": color, "description": description}
    updated = False
    for i, lbl in enumerate(existing):
        if lbl.get("name") == label_name:
            if lbl.get("description") != description or lbl.get("color") != color:
                existing[i] = entry
                updated = True
            break
    else:
        existing.append(entry)
        updated = True

    if updated:
        try:
            labels_file.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass  # best-effort


def _ensure_milestone_labels_for_all(milestones: list[dict]) -> None:
    """Call _ensure_milestone_label for every milestone in the list."""
    for m in milestones:
        _ensure_milestone_label(m["number"], m["title"])


def _milestones_dir(root: Path) -> Path:
    return root / "hub_agents" / "milestones"


def _milestone_knowledge_path(root: Path, milestone_number: int) -> Path:
    return _milestones_dir(root) / f"M{milestone_number}.md"


def _milestone_index_path(root: Path) -> Path:
    return _milestones_dir(root) / "milestone_index.json"


def _load_milestone_index(root: Path) -> dict:
    path = _milestone_index_path(root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_milestone_index(root: Path, index: dict) -> None:
    path = _milestone_index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    from extensions.gh_management.github_planner.storage import _atomic_write
    _atomic_write(path, json.dumps(index, indent=2))


def _update_milestone_enables_depends(root: Path, new_number: int) -> None:
    """Update Enables/Depends On in adjacent milestone knowledge files."""
    from extensions.gh_management.github_planner.storage import _atomic_write

    index = _load_milestone_index(root)

    new_title = index.get(str(new_number), {}).get("title", f"M{new_number}")
    new_ref = f"M{new_number} — {new_title}"

    prior_number = new_number - 1
    if prior_number >= 1 and str(prior_number) in index:
        prior_path = _milestone_knowledge_path(root, prior_number)
        if prior_path.exists():
            text = prior_path.read_text(encoding="utf-8")
            lines = text.splitlines(keepends=True)
            new_lines = []
            in_enables = False
            for line in lines:
                if re.match(r"^## Enables", line):
                    in_enables = True
                    new_lines.append(line)
                    continue
                if in_enables:
                    if line.startswith("## "):
                        in_enables = False
                        new_lines.append(f"{new_ref}\n")
                        new_lines.append(line)
                    else:
                        continue
                else:
                    new_lines.append(line)
            if in_enables:
                new_lines.append(f"{new_ref}\n")
            _atomic_write(prior_path, "".join(new_lines))

    next_number = new_number + 1
    if str(next_number) in index:
        next_path = _milestone_knowledge_path(root, next_number)
        if next_path.exists():
            text = next_path.read_text(encoding="utf-8")
            lines = text.splitlines(keepends=True)
            new_lines = []
            in_depends = False
            for line in lines:
                if re.match(r"^## Depends On", line):
                    in_depends = True
                    new_lines.append(line)
                    continue
                if in_depends:
                    if line.startswith("## "):
                        in_depends = False
                        new_lines.append(f"{new_ref}\n")
                        new_lines.append(line)
                    else:
                        continue
                else:
                    new_lines.append(line)
            if in_depends:
                new_lines.append(f"{new_ref}\n")
            _atomic_write(next_path, "".join(new_lines))


def _sync_milestone_to_project_summary(root: Path, milestone_number: int, title: str, description: str) -> None:
    """Update the Milestones table row in project_summary.md for this milestone."""
    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir, _PROJECT_DOCS_CACHE
    from extensions.gh_management.github_planner.storage import _atomic_write

    docs_dir = _gh_planner_docs_dir(root)
    summary_path = docs_dir / "project_summary.md"
    if not summary_path.exists():
        return

    text = summary_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(\|\s*M" + str(milestone_number) + r"\s*\|[^\n]*\n)"
    )
    goal_sentence = description.split(".")[0].strip() if description else ""
    new_row = f"| M{milestone_number} | {title} | {goal_sentence} |\n"

    if pattern.search(text):
        updated = pattern.sub(new_row, text)
        if updated != text:
            _atomic_write(summary_path, updated)
            _PROJECT_DOCS_CACHE.pop(str(root), None)


def _check_detail_gaps(detail_sections: dict, milestone_title: str) -> list[str]:
    """Return section names from detail that might be relevant but missing content."""
    gaps = []
    if not detail_sections:
        gaps.append("project_detail.md not found")
    return gaps


def _do_list_milestones(state: str = "open") -> dict:
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    repo = _p.read_env(root).get("GITHUB_REPO", "")
    if repo in _MILESTONE_CACHE:
        ms = _MILESTONE_CACHE[repo]
        lines = "\n".join(f"  M{m['number']} — {m['title']}: {m.get('description','')}" for m in ms)
        return {"milestones": ms, "count": len(ms), "cached": True,
                "_display": f"{len(ms)} milestones (cached):\n{lines}"}
    gh, err = _p.get_github_client()
    if gh is None:
        return err
    try:
        with gh:
            raw = gh.list_milestones(state=state)
        ms = [{"number": m["number"], "title": m["title"],
               "description": m.get("description", ""),
               "open_issues": m.get("open_issues", 0)} for m in raw]
        _MILESTONE_CACHE[repo] = ms
        _p._ensure_milestone_labels_for_all(ms)
        lines = "\n".join(f"  M{m['number']} — {m['title']}: {m['description']}" for m in ms)
        return {"milestones": ms, "count": len(ms), "cached": False,
                "_display": f"{len(ms)} milestones on {repo}:\n{lines}"}
    except Exception as exc:
        return {"error": "list_milestones_failed", "message": str(exc)}


def _do_create_milestone(title: str, description: str = "", due_on: str | None = None) -> dict:
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    if not title:
        return {"error": "missing_field", "message": "title is required"}
    gh, err = _p.get_github_client()
    if gh is None:
        return err
    repo = _p.read_env(root).get("GITHUB_REPO", "")
    try:
        with gh:
            m = gh.create_milestone(title, description, due_on)
        entry = {"number": m["number"], "title": m["title"],
                 "description": m.get("description", ""),
                 "open_issues": m.get("open_issues", 0)}
        cache = _MILESTONE_CACHE.setdefault(repo, [])
        if not any(x["number"] == entry["number"] for x in cache):
            cache.append(entry)
        _p._ensure_milestone_label(entry["number"], entry["title"])
        return {
            "number": entry["number"],
            "title": entry["title"],
            "description": entry["description"],
            "_display": f"✅ **Milestone M{entry['number']}:** {entry['title']} on {repo}",
        }
    except Exception as exc:
        return {"error": "create_milestone_failed", "message": str(exc)}


def _do_assign_milestone(slug: str, milestone_number: int) -> dict:
    from extensions.gh_management.github_planner.storage import read_issue_frontmatter, _issues_dir, _atomic_write
    import yaml as _yaml
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    repo = _p.read_env(root).get("GITHUB_REPO", "")
    ms = _MILESTONE_CACHE.get(repo, [])
    milestone_title = next((m["title"] for m in ms if m["number"] == milestone_number), None)

    fm = read_issue_frontmatter(root, slug)
    if not fm:
        return {"error": "issue_not_found", "message": f"No issue for slug {slug!r}"}
    gh_number = fm.get("issue_number")

    if gh_number:
        gh, err = _p.get_github_client()
        if gh is None:
            return err
        try:
            with gh:
                gh.update_issue_milestone(gh_number, milestone_number)
        except Exception as exc:
            return {"error": "assign_milestone_failed", "message": str(exc)}

    path = _issues_dir(root) / f"{slug}.md"
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    raw_fm = _yaml.safe_load(parts[1]) or {}
    raw_fm["milestone_number"] = milestone_number
    if milestone_title:
        raw_fm["milestone_title"] = milestone_title
    body = parts[2] if len(parts) > 2 else ""
    _atomic_write(path, f"---\n{_yaml.dump(raw_fm, default_flow_style=False)}---{body}")

    return {
        "slug": slug,
        "milestone_number": milestone_number,
        "milestone_title": milestone_title,
        "github_assigned": bool(gh_number),
        "_display": f"✓ #{slug} → M{milestone_number} — {milestone_title or '(unknown)'}",
    }


def _do_generate_milestone_knowledge(milestone_number: int) -> dict:
    """Generate a structured knowledge file for a milestone."""
    from extensions.gh_management.github_planner.project_docs import (
        _gh_planner_docs_dir, _PROJECT_DOCS_CACHE, _parse_h2_sections
    )
    from extensions.gh_management.github_planner.storage import _atomic_write
    from datetime import datetime, timezone
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    repo = _p.read_env(root).get("GITHUB_REPO", "")
    cached_milestones = _MILESTONE_CACHE.get(repo, [])
    milestone_entry = next((m for m in cached_milestones if m["number"] == milestone_number), None)

    if milestone_entry is None:
        title = f"M{milestone_number}"
        description = ""
    else:
        title = milestone_entry.get("title", f"M{milestone_number}")
        description = milestone_entry.get("description", "")

    resolved = _p._resolve_repo(None) or "unknown"
    cached_docs = _PROJECT_DOCS_CACHE.get(resolved)
    if cached_docs:
        summary_text = cached_docs.get("summary") or ""
        detail_text = cached_docs.get("detail") or ""
        detail_sections = cached_docs.get("_sections") or {}
    else:
        docs_dir = _gh_planner_docs_dir(root)
        summary_path = docs_dir / "project_summary.md"
        detail_path = docs_dir / "project_detail.md"
        summary_text = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
        detail_text = detail_path.read_text(encoding="utf-8") if detail_path.exists() else ""
        detail_sections = _parse_h2_sections(detail_text) if detail_text else {}

    summary_sections = _parse_h2_sections(summary_text) if summary_text else {}
    design_principles = summary_sections.get("Design Principles", "").strip()
    interface_layers = summary_sections.get("Interface Layers", "").strip()

    index = _load_milestone_index(root)

    prior_number = milestone_number - 1
    prior_entry = index.get(str(prior_number))
    if prior_entry:
        depends_on = f"M{prior_number} — {prior_entry['title']}"
    else:
        depends_on = "None (first milestone)"

    next_number = milestone_number + 1
    next_entry = index.get(str(next_number))
    if next_entry:
        enables = f"M{next_number} — {next_entry['title']}"
    else:
        enables = "None (last milestone)"

    planned_features_text = summary_sections.get("Planned Features", "").strip()
    if not planned_features_text:
        features_governed = "*(see project_summary.md)*"
    else:
        feature_lines = [
            line for line in planned_features_text.splitlines()
            if line.strip().startswith("-") or line.strip().startswith("*")
        ]
        features_governed = "\n".join(feature_lines[:10]) if feature_lines else planned_features_text[:500]

    if detail_sections:
        section_names = list(detail_sections.keys())[:5]
        interface_contract = "\n".join(f"- {s}" for s in section_names) if section_names else "*(see project_detail.md)*"
    else:
        interface_contract = "*(see project_detail.md)*"

    relevant_principles = design_principles if design_principles else "*(see project_summary.md Design Principles)*"

    content = f"""# M{milestone_number} — {title}

## Goal
{description if description else "*(no description provided)*"}

## Features Governed
{features_governed}

## Interface Contract
{interface_contract}

## Depends On
{depends_on}

## Enables
{enables}

## Design Principles Applicable
{relevant_principles}
"""

    milestones_path = _milestone_knowledge_path(root, milestone_number)
    milestones_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(milestones_path, content)

    index[str(milestone_number)] = {
        "title": title,
        "path": f"milestones/M{milestone_number}.md",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_milestone_index(root, index)

    _sync_milestone_to_project_summary(root, milestone_number, title, description)

    gaps = _check_detail_gaps(detail_sections, title)

    _update_milestone_enables_depends(root, milestone_number)

    display = f"✅ **M{milestone_number} knowledge file** written — {title}"
    if gaps:
        display += f"\n⚠️ Detail gaps: {', '.join(gaps)}"

    return {
        "milestone_number": milestone_number,
        "path": str(milestones_path),
        "_display": display,
    }


def _do_load_milestone_knowledge(milestone_number: int) -> dict:
    """Load the knowledge file for a milestone."""
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    path = _milestone_knowledge_path(root, milestone_number)
    if not path.exists():
        return {
            "exists": False,
            "milestone_number": milestone_number,
            "_display": f"⚠️ M{milestone_number} knowledge not yet generated — call generate_milestone_knowledge({milestone_number})",
        }

    content = path.read_text(encoding="utf-8")
    return {
        "milestone_number": milestone_number,
        "content": content,
        "exists": True,
        "_display": f"📄 Loaded M{milestone_number} knowledge",
    }
