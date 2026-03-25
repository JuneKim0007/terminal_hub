"""Skill registry helpers — parsing, loading, updating, docs map."""
# stdlib
import json
import re
from pathlib import Path


def _pkg():
    """Return the github_planner package module so patches applied by tests are respected."""
    import sys
    return sys.modules['extensions.gh_management.github_planner']

# ── Constants ─────────────────────────────────────────────────────────────────
_SKILL_REGISTRY: dict[str, dict] = {}

_PLUGIN_DIR = Path(__file__).parent
_COMMANDS_DIR = _PLUGIN_DIR / "commands"


def _parse_skill_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from a skill .md file. Returns {} if no frontmatter."""
    try:
        import yaml as _yaml
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return {}
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}
        return _yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


def _parse_skills_dir(skills_dir: Path, registry: dict, tier: str) -> None:
    """Read each *.md file in skills_dir (excluding SKILLS.md), parse frontmatter, add to registry."""
    if not skills_dir.exists():
        return
    for f in sorted(skills_dir.glob("*.md")):
        if f.name == "SKILLS.md":
            continue
        fm = _parse_skill_frontmatter(f)
        name = fm.get("name") or f.stem
        if name not in registry or tier == "project":
            registry[name] = {
                "path": str(f),
                "alwaysApply": fm.get("alwaysApply", False),
                "triggers": fm.get("triggers", []),
                "tier": tier,
            }


def _load_skill_registry(root: Path) -> dict:
    """Merge plugin-level Tier 1 and project-level Tier 2 skills into _SKILL_REGISTRY[root]."""
    from extensions.gh_management.github_planner.project_docs import _load_docs_config

    registry: dict = {}
    plugin_skills_dir = Path(__file__).parent / "skills"
    _parse_skills_dir(plugin_skills_dir, registry, tier="plugin")
    config = _load_docs_config(root)
    skills_index = config.get("skills")
    if skills_index:
        project_skills_path = root / skills_index
        if project_skills_path.exists():
            _parse_skills_dir(project_skills_path.parent, registry, tier="project")
    _SKILL_REGISTRY[str(root)] = registry
    return registry


def _update_skills_registry(
    root: Path,
    name: str,
    tier: str,
    always_apply: bool,
    triggers: list[str],
) -> bool:
    """Append a new skill row to the appropriate SKILLS.md registry atomically."""
    from extensions.gh_management.github_planner.storage import _atomic_write

    if tier == "plugin":
        registry_path = Path(__file__).parent / "skills" / "SKILLS.md"
    else:
        registry_path = root / "hub_agents" / "skills" / "SKILLS.md"

    if not registry_path.exists():
        return False

    text = registry_path.read_text(encoding="utf-8")
    if f"| {name} |" in text:
        return True

    new_row = f"| {name} | {name}.md | {str(always_apply).lower()} | {', '.join(triggers[:3])} |"
    if "Load on demand:" in text:
        text = text.replace("Load on demand:", f"{new_row}\n\nLoad on demand:")
    else:
        text = text.rstrip() + f"\n{new_row}\n"

    _atomic_write(registry_path, text)

    _SKILL_REGISTRY.pop(str(root), None)
    return True


def _silent_skill_detection(root: Path) -> None:
    """Run skill detection silently. No-op when no candidates found."""
    try:
        candidates = _do_update_skill_detection(root)
        if candidates:
            pass
    except Exception:
        pass


def _do_load_skill(name: str) -> dict:
    """Load a skill file from the registry by name."""
    root = _pkg().get_workspace_root()
    registry = _SKILL_REGISTRY.get(str(root)) or _load_skill_registry(root)
    entry = registry.get(name)
    if not entry:
        available = sorted(registry.keys())
        return {
            "error": "skill_not_found",
            "message": f"No skill {name!r} in registry.",
            "available": available,
        }
    content = Path(entry["path"]).read_text(encoding="utf-8")
    return {
        "name": name,
        "content": content,
        "tier": entry["tier"],
        "_display": f"✅ **Skill loaded:** `{name}` ({entry['tier']})",
    }


def _do_update_skill_detection(root: Path) -> list[dict]:
    """Scan for knowledge that should be extracted into skill files."""
    import re as _re
    candidates = []
    registry = _SKILL_REGISTRY.get(str(root)) or {}

    commands_dirs = [
        Path(__file__).parent.parent / "gh_implementation" / "commands",
        Path(__file__).parent / "commands",
    ]
    for commands_dir in commands_dirs:
        if not commands_dir.exists():
            continue
        for md_file in sorted(commands_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            blocks = _re.split(r"<!-- SKILL:.*?-->", text)
            for block in blocks:
                lines = [l for l in block.split("\n") if l.strip() and not l.strip().startswith("#")]
                if len(lines) > 50:
                    first_heading = _re.search(r"^#+\s+(.+)", block, _re.MULTILINE)
                    topic = first_heading.group(1) if first_heading else "inline block"
                    topic_lower = topic.lower()
                    if not any(topic_lower in k or k in topic_lower for k in registry):
                        candidates.append({
                            "source": str(md_file.relative_to(Path(__file__).parent.parent.parent)),
                            "candidate_description": f"Inline knowledge block: {topic} ({len(lines)} lines)",
                            "domain": topic,
                        })

    issues_dir = root / "hub_agents" / "issues"
    if issues_dir.exists():
        domain_counts: dict[str, int] = {}
        for issue_file in issues_dir.glob("*.md"):
            try:
                text = issue_file.read_text(encoding="utf-8")
            except OSError:
                continue
            for domain in ["auth", "crud", "search", "upload", "export", "notification", "payment", "analytics"]:
                if domain in text.lower():
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1

        for domain, count in domain_counts.items():
            if count >= 3 and domain not in registry:
                candidates.append({
                    "source": "open issues",
                    "candidate_description": f"Domain '{domain}' referenced in {count} issues but no skill exists",
                    "domain": domain,
                })

    return candidates


def _do_update_skill_create(
    root: Path,
    name: str,
    description: str | None,
    content_hints: list[str] | None,
    source_doc: str | None,
    dry_run: bool,
) -> dict:
    """Create a new skill file and update SKILLS.md registry."""
    import re as _re_sk

    skill_dir = Path(__file__).parent / "skills"
    skill_path = skill_dir / f"{name}.md"

    if not description:
        description = f"Rules for {name}. Load when working on {name}-related tasks."

    hints_text = ""
    if content_hints:
        hints_text = "\n".join(f"- {h}" for h in content_hints)

    triggers = content_hints[:5] if content_hints else [name]
    triggers_yaml = "[" + ", ".join(triggers) + "]"

    skill_content = f"""---
name: {name}
description: {description}
alwaysApply: false
triggers: {triggers_yaml}
---

# {name}

## When to Use

- When working on {name}-related features
- When implementing tasks tagged with: {', '.join(triggers[:3])}

## When NOT to Use

- For unrelated domains (use the relevant domain skill instead)
- For trivial single-line changes

## Rules / Knowledge

{hints_text or f'<!-- Add rules for {name} here -->'}

## Examples

<!-- Add before/after or correct/incorrect examples here -->
"""

    source_doc_updated = None
    if not dry_run:
        from extensions.gh_management.github_planner.storage import _atomic_write
        _atomic_write(skill_path, skill_content)
        _update_skills_registry(root, name, "plugin", False, triggers)

        if source_doc:
            source_path = Path(__file__).parent.parent.parent / source_doc
            if source_path.exists():
                source_text = source_path.read_text(encoding="utf-8")
                replacement = f'\n<!-- SKILL: load_skill("{name}") — {description[:80]} -->\n'
                for hint in (content_hints or []):
                    pattern = _re_sk.compile(
                        rf"(##\s+[^\n]*{_re_sk.escape(hint)}[^\n]*\n)(.{{50,}}?)(\n##|\Z)",
                        _re_sk.IGNORECASE | _re_sk.DOTALL,
                    )
                    m = pattern.search(source_text)
                    if m:
                        from extensions.gh_management.github_planner.storage import _atomic_write as _aw
                        source_text = source_text[:m.start(2)] + replacement + source_text[m.end(2):]
                        _aw(source_path, source_text)
                        source_doc_updated = source_doc
                        break

    return {
        "name": name,
        "path": str(skill_path.relative_to(Path(__file__).parent.parent.parent)),
        "tier": "plugin",
        "registry_updated": not dry_run,
        "source_doc_updated": source_doc_updated,
        "dry_run": dry_run,
        "_display": f"{'[dry-run] ' if dry_run else ''}✅ **Skill created:** `{name}` — added to SKILLS.md registry",
    }


def _do_update_skill(
    name: str | None,
    description: str | None,
    content_hints: list[str] | None,
    source_doc: str | None,
    dry_run: bool,
) -> dict:
    """MCP tool implementation for update_skill."""
    root = _pkg().get_workspace_root()

    if name is None:
        candidates = _do_update_skill_detection(root)
        if not candidates:
            return {"candidates": [], "message": "No skill candidates found — codebase is clean", "_display": ""}
        return {
            "candidates": candidates,
            "message": f"Found {len(candidates)} skill candidate(s)",
            "_display": f"🔍 **Skill candidates found:** {len(candidates)} — call update_skill(name=...) to create",
        }
    else:
        return _do_update_skill_create(root, name, description, content_hints, source_doc, dry_run)


def _docs_map_is_stale(map_path: Path) -> bool:
    """Return True if any skills/ or commands/ file is newer than docs_map.json."""
    if not map_path.exists():
        return True
    _p = _pkg()
    map_mtime = map_path.stat().st_mtime
    for directory in (_p._PLUGIN_DIR / "skills", _p._COMMANDS_DIR):
        if not directory.exists():
            continue
        for f in directory.rglob("*.md"):
            if f.stat().st_mtime > map_mtime:
                return True
    return False


def _do_build_docs_map() -> dict:
    """Scan plugin skills + command files, build docs_map.json in the plugin directory."""
    from extensions.gh_management.github_planner.storage import _atomic_write
    _p = _pkg()

    skills_dir = _p._PLUGIN_DIR / "skills"
    skill_ref = re.compile(r'load_skill\(["\']([^"\']+)["\']\)')
    tool_ref = re.compile(r'`([a-z][a-z_]{2,})\s*\(')

    skills_data: dict[str, dict] = {}
    for f in sorted(skills_dir.glob("*.md")):
        if f.name == "SKILLS.md":
            continue
        fm = _parse_skill_frontmatter(f)
        name = fm.get("name") or f.stem
        skills_data[name] = {
            "file": f"skills/{f.name}",
            "alwaysApply": fm.get("alwaysApply", False),
            "triggers": fm.get("triggers", []),
            "used_by_commands": [],
        }

    commands_data: dict[str, dict] = {}
    for f in sorted(_p._COMMANDS_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        skills_loaded = sorted(set(skill_ref.findall(text)))
        tools_referenced = sorted(set(tool_ref.findall(text)))
        entry_match = re.search(r"^# (/th:[^\s\n]+)", text, re.MULTILINE)
        entry_point = entry_match.group(1) if entry_match else f.stem
        commands_data[f.name] = {
            "entry_point": entry_point,
            "loads_skills": skills_loaded,
            "tools_referenced": tools_referenced,
        }
        for skill_name in skills_loaded:
            if skill_name in skills_data and f.name not in skills_data[skill_name]["used_by_commands"]:
                skills_data[skill_name]["used_by_commands"].append(f.name)

    docs_map = {"skills": skills_data, "commands": commands_data}
    map_path = _p._PLUGIN_DIR / "docs_map.json"
    _atomic_write(map_path, json.dumps(docs_map, indent=2))

    return {
        "skills": skills_data,
        "commands": commands_data,
        "_display": f"✅ **docs_map.json built** — {len(skills_data)} skills, {len(commands_data)} commands",
    }


def _do_get_docs_map(view: str) -> dict:
    """Read docs_map.json; auto-rebuild if missing or any skills/commands file changed."""
    map_path = _pkg()._PLUGIN_DIR / "docs_map.json"
    if _docs_map_is_stale(map_path):
        result = _do_build_docs_map()
        data = {"skills": result["skills"], "commands": result["commands"]}
    else:
        data = json.loads(map_path.read_text(encoding="utf-8"))

    if view == "skills":
        lines = ["**Skill Map** — all skills and where they are loaded\n"]
        lines.append(f"{'Skill':<32} {'Used by':<30} {'Always':<8} Triggers")
        lines.append("─" * 100)
        for name, info in sorted(data["skills"].items()):
            used = ", ".join(info["used_by_commands"]) or "(none)"
            always = "yes" if info["alwaysApply"] else "no"
            triggers = ", ".join(info["triggers"][:3]) if info["triggers"] else "—"
            if len(used) > 28:
                used = used[:25] + "..."
            lines.append(f"{name:<32} {used:<30} {always:<8} {triggers}")
        display = "\n".join(lines)
    else:
        lines = ["**Command Map** — commands and their skill + tool dependencies\n"]
        lines.append(f"{'Command':<28} {'Skills loaded':<38} Tools referenced")
        lines.append("─" * 100)
        for name, info in sorted(data["commands"].items()):
            skills = ", ".join(info["loads_skills"]) or "(none)"
            tools = ", ".join(info["tools_referenced"][:5]) or "(none)"
            if len(skills) > 36:
                skills = skills[:33] + "..."
            lines.append(f"{name:<28} {skills:<38} {tools}")
        display = "\n".join(lines)

    return {"view": view, "data": data, "_display": display}
