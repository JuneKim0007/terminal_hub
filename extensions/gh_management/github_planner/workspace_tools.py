"""Workspace utility helpers — docs detection, plugin state, unload policy, preferences."""
# stdlib
import json
import os
import re
from pathlib import Path


def _pkg():
    """Return the github_planner package module so patches applied by tests are respected."""
    import sys
    return sys.modules['extensions.gh_management.github_planner']

# ── Constants ─────────────────────────────────────────────────────────────────
_DOC_LIKE_PATTERNS = frozenset([
    "readme", "design", "architecture", "spec", "contributing",
    "changelog", "changes", "history", "docs/", "documentation/",
])

_DOCS_NOISE_PATTERNS = {
    "CHANGELOG", "CHANGELOG.md", "LICENSE", "LICENSE.md", "LICENCE",
    "package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock",
}
_DOCS_NOISE_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}

_GH_PLANNER_VOLATILE_FILES = [
    "analyzer_snapshot.json",
    "file_hashes.json",
    "file_tree.json",
    "github_local_config.json",
]

_PLUGIN_DIR = Path(__file__).parent
_UNLOAD_POLICY_PATH = _PLUGIN_DIR / "unload_policy.json"

_MD_SUFFIXES = {".md", ".rst", ".txt"}

_ALLOWED_PREFERENCES = {"confirm_arch_changes", "github_repo_connected", "milestone_assign"}


def _load_unload_policy() -> dict:
    """Load and return the full unload_policy.json contents."""
    try:
        policy = json.loads(_UNLOAD_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": str(exc), "commands": {}}

    from extensions.gh_management.github_planner.analysis import _ANALYSIS_CACHE, _FILE_TREE_CACHE
    from extensions.gh_management.github_planner.project_docs import _PROJECT_DOCS_CACHE, _SESSION_HEADER_CACHE
    from extensions.gh_management.github_planner.labels import _LABEL_CACHE, _LABEL_ANALYSIS_CACHE
    from extensions.gh_management.github_planner.milestones import _MILESTONE_CACHE
    from extensions.gh_management.github_planner.setup import _REPO_CACHE
    from extensions.gh_management.github_planner.session import _SESSION_REPO_CONFIRMED

    _CACHE_KEY_MAP: dict[str, tuple] = {
        "analysis_cache":            (_ANALYSIS_CACHE,          None),
        "project_docs_cache":        (_PROJECT_DOCS_CACHE,      None),
        "file_tree_cache":           (_FILE_TREE_CACHE,          None),
        "session_header_cache":      (_SESSION_HEADER_CACHE,    None),
        "label_cache":               (_LABEL_CACHE,             None),
        "label_analysis_cache":      (_LABEL_ANALYSIS_CACHE,   None),
        "milestone_cache":           (_MILESTONE_CACHE,         None),
        "repo_cache":                (_REPO_CACHE,              None),
        "session_repo_confirmation": (_SESSION_REPO_CONFIRMED,  None),
        "analyzer_snapshot":         (None, "analyzer_snapshot.json"),
        "file_hashes":               (None, "file_hashes.json"),
        "file_tree":                 (None, "file_tree.json"),
        "github_local_config":       (None, "github_local_config.json"),
        "docs_strategy":             (None, "docs_strategy.json"),
        "docs_config":               (None, "docs_config.json"),
    }

    known_keys = set(_CACHE_KEY_MAP.keys()) | set(policy.get("cache_keys", {}).keys())
    for cmd_name, cmd_policy in policy.get("commands", {}).items():
        for key in cmd_policy.get("unload", []) + cmd_policy.get("keep", []):
            if key not in known_keys:
                import warnings
                warnings.warn(
                    f"unload_policy.json: command {cmd_name!r} references unknown cache key {key!r}",
                    stacklevel=2,
                )
    return policy


def detect_existing_docs(file_index: list[dict]) -> list[dict]:
    """From analyze_repo_full file_index, return doc-like .md files."""
    results = []
    for f in file_index:
        path: str = f.get("path", "").lower()
        if not path.endswith(".md"):
            continue
        base = path.rsplit("/", 1)[-1].rstrip(".md").lower() if "/" in path else path.rstrip(".md").lower()
        if any(pat in path or base.startswith(pat.rstrip("/")) for pat in _DOC_LIKE_PATTERNS):
            results.append({"path": f["path"], "size": f.get("size", 0)})
    return results


def _do_set_preference(key: str, value: bool) -> dict:
    """Persist a user preference in hub_agents/config.yaml."""
    from terminal_hub.config import write_preference
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    if key not in _ALLOWED_PREFERENCES:
        return {
            "error": "unknown_preference",
            "message": f"Unknown preference {key!r}. Valid keys: {sorted(_ALLOWED_PREFERENCES)}",
            "_hook": None,
        }
    write_preference(root, key, value)
    label = "on" if value else "off"
    return {"key": key, "value": value, "_display": f"✓ Preference '{key}' set to {label}"}


def _do_create_github_repo(name: str, description: str, private: bool) -> dict:
    """Create a new GitHub repo under the authenticated user, then call setup_workspace."""
    from extensions.gh_management.github_planner.client import GitHubError
    from terminal_hub.config import write_preference
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    token, source = _p.resolve_token()
    if token is None:
        return {
            "error": "github_unavailable",
            "message": source.suggestion(),
            "_guidance": _p._G_AUTH,
            "_hook": None,
        }

    try:
        data = _p.create_user_repo(token=token, name=name, description=description, private=private)
    except GitHubError as exc:
        return {"error": exc.error_code, "message": str(exc), "_hook": None}

    full_name = data.get("full_name", f"unknown/{name}")
    html_url = data.get("html_url", "")

    from terminal_hub.config import save_config, WorkspaceMode
    from terminal_hub.env_store import write_env as _write_env
    _write_env(root, {"GITHUB_REPO": full_name})
    save_config(root, WorkspaceMode.GITHUB, full_name)
    write_preference(root, "github_repo_connected", True)
    _p._invalidate_repo_cache()

    return {
        "success": True,
        "github_repo": full_name,
        "url": html_url,
        "private": private,
        "_display": f"✅ **Repo created:** `{full_name}` ({'private' if private else 'public'})",
    }


def _do_save_docs_strategy(
    strategy: str,
    referred_docs: list[str] | None = None,
) -> dict:
    """Persist existing-docs strategy to hub_agents/extensions/gh_planner/docs_strategy.json (#84)."""
    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    valid = {"refer", "overwrite", "merge", "ignore"}
    if strategy not in valid:
        return {"error": "invalid_strategy", "message": f"strategy must be one of {sorted(valid)}"}

    docs_dir = _gh_planner_docs_dir(root)
    docs_dir.mkdir(parents=True, exist_ok=True)
    strategy_path = docs_dir / "docs_strategy.json"

    data: dict = {"strategy": strategy}
    if strategy == "refer" and referred_docs:
        data["referred_docs"] = referred_docs

    tmp = strategy_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    import os as _os4; _os4.replace(tmp, strategy_path)

    return {
        "saved": True,
        "strategy": strategy,
        "file": str(strategy_path.relative_to(root)),
        "_display": f"✓ Docs strategy saved: {strategy}",
    }


def _do_load_docs_strategy() -> dict:
    """Load existing-docs strategy from disk, or return default (#84)."""
    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    strategy_path = _gh_planner_docs_dir(root) / "docs_strategy.json"
    if not strategy_path.exists():
        return {"strategy": None, "referred_docs": []}
    try:
        data = json.loads(strategy_path.read_text(encoding="utf-8"))
        return {"strategy": data.get("strategy"), "referred_docs": data.get("referred_docs", [])}
    except (json.JSONDecodeError, OSError):
        return {"strategy": None, "referred_docs": []}


def _do_search_project_docs() -> dict:
    root = _pkg().get_workspace_root()
    candidates = []
    noise_upper = {p.upper() for p in _DOCS_NOISE_PATTERNS}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _DOCS_NOISE_DIRS]
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            if fname in _DOCS_NOISE_PATTERNS:
                continue
            if fname.upper() in noise_upper:
                continue
            fpath = Path(dirpath) / fname
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            headings = [l.lstrip("#").strip() for l in text.splitlines() if l.startswith("#")][:5]
            size_kb = round(fpath.stat().st_size / 1024, 1)
            rel = str(fpath.relative_to(root))
            score = size_kb + len(headings) * 0.5
            candidates.append({"path": rel, "size_kb": size_kb, "headings": headings, "_score": score})
    candidates.sort(key=lambda x: x["_score"], reverse=True)
    for c in candidates:
        del c["_score"]
    display_lines = [f"  {c['path']} ({c['size_kb']}KB)" for c in candidates[:10]]
    display = "Found " + str(len(candidates)) + " doc candidates:\n" + "\n".join(display_lines)
    return {"candidates": candidates[:20], "total": len(candidates), "_display": display}


def _do_connect_docs(
    primary: str | None = None,
    detail: str | None = None,
    skills: str | None = None,
    others: list[str] | None = None,
) -> dict:
    from extensions.gh_management.github_planner.project_docs import _load_docs_config, _save_docs_config
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    others = others or []
    for ref_path in others:
        p = root / ref_path
        if not p.exists():
            return {
                "error": "ref_not_found",
                "path": ref_path,
                "_display": f"⚠️ **Not found:** `{ref_path}`",
            }
    config = _load_docs_config(root)
    config["primary"] = primary or "hub_agents/project_summary.md"
    config["detail"] = detail or "hub_agents/project_detail.md"
    config["skills"] = skills
    config["others"] = others
    _save_docs_config(root, config)
    parts = []
    if skills:
        parts.append(f"skills: `{skills}`")
    if others:
        parts.append(f"{len(others)} other ref(s)")
    display = "✅ **Docs connected:** " + (", ".join(parts) if parts else "defaults configured")
    return {"connected": True, "config": config, "_display": display}


def _do_load_connected_docs(section: str | None = None) -> dict:
    from extensions.gh_management.github_planner.project_docs import _load_docs_config

    root = _pkg().get_workspace_root()
    config = _load_docs_config(root)
    others = config.get("others") or []
    if not others:
        return {
            "content": None,
            "_display": "⚠️ No reference docs connected. Call connect_docs(others=[...]) first.",
        }
    texts = []
    paths_loaded = []
    for ref_path in others:
        path = root / ref_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if section:
            pattern = rf"(?m)^##\s+{re.escape(section)}.*?(?=^##\s|\Z)"
            m = re.search(pattern, text, re.DOTALL | re.MULTILINE)
            if m:
                texts.append(m.group(0))
                paths_loaded.append(ref_path)
        else:
            texts.append(text)
            paths_loaded.append(ref_path)
    if not texts:
        return {
            "content": None,
            "_display": f"⚠️ No content found{f' for section `{section}`' if section else ''}",
        }
    combined = "\n\n".join(texts)
    size = len(combined)
    display = f"📄 **Loaded:** {', '.join(f'`{p}`' for p in paths_loaded)} ({size} chars)"
    if section:
        display += f" — section `{section}`"
    return {"content": combined, "paths": paths_loaded, "_display": display}


def _do_list_plugin_state(plugin: str) -> dict:
    """Inventory all gh_planner-managed resources: in-memory caches + disk files."""
    if plugin != "gh_planner":
        return {"error": "unknown_plugin", "message": f"Unknown plugin {plugin!r}. Available: gh_planner"}

    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir, _PROJECT_DOCS_CACHE, _SESSION_HEADER_CACHE
    from extensions.gh_management.github_planner.analysis import _ANALYSIS_CACHE, _FILE_TREE_CACHE
    from extensions.gh_management.github_planner.labels import _LABEL_CACHE

    root = _pkg().get_workspace_root()
    docs_dir = _gh_planner_docs_dir(root)

    caches = []
    if _ANALYSIS_CACHE:
        caches.append({"name": "_ANALYSIS_CACHE", "entries": len(_ANALYSIS_CACHE)})
    if _PROJECT_DOCS_CACHE:
        caches.append({"name": "_PROJECT_DOCS_CACHE", "entries": len(_PROJECT_DOCS_CACHE)})
    if _FILE_TREE_CACHE:
        caches.append({"name": "_FILE_TREE_CACHE", "fetched_at": _FILE_TREE_CACHE.get("fetched_at")})
    if _SESSION_HEADER_CACHE:
        caches.append({"name": "_SESSION_HEADER_CACHE", "entries": len(_SESSION_HEADER_CACHE)})
    if _LABEL_CACHE:
        caches.append({"name": "_LABEL_CACHE", "entries": len(_LABEL_CACHE)})

    disk_files = []
    for fname in _GH_PLANNER_VOLATILE_FILES:
        p = docs_dir / fname
        if p.exists():
            disk_files.append({"path": str(p.relative_to(root)), "size_bytes": p.stat().st_size})

    def _dict_size_kb(d: dict) -> int:
        try:
            import sys
            return sys.getsizeof(str(d)) // 1024
        except Exception:
            return 0

    estimated_kb = (
        _dict_size_kb(_ANALYSIS_CACHE)
        + _dict_size_kb(_PROJECT_DOCS_CACHE)
        + _dict_size_kb(_FILE_TREE_CACHE)
        + _dict_size_kb(_SESSION_HEADER_CACHE)
        + _dict_size_kb(_LABEL_CACHE)
    )
    _SUGGEST_UNLOAD_KB = 500

    result = {
        "plugin": plugin,
        "caches": caches,
        "disk_files": disk_files,
        "total_caches": len(caches),
        "total_disk_files": len(disk_files),
        "estimated_memory_kb": estimated_kb,
        "_display": (
            f"gh_planner state: {len(caches)} in-memory cache(s), "
            f"{len(disk_files)} disk file(s), ~{estimated_kb}KB memory"
        ),
    }
    if estimated_kb >= _SUGGEST_UNLOAD_KB:
        result["suggest_unload"] = True
    return result


def _do_unload_plugin(plugin: str) -> dict:
    """Clear all gh_planner in-memory caches and volatile disk files."""
    if plugin != "gh_planner":
        return {"error": "unknown_plugin", "message": f"Unknown plugin {plugin!r}. Available: gh_planner"}

    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir, _PROJECT_DOCS_CACHE, _SESSION_HEADER_CACHE
    from extensions.gh_management.github_planner.analysis import _ANALYSIS_CACHE, _FILE_TREE_CACHE
    from extensions.gh_management.github_planner.labels import _LABEL_CACHE, _LABEL_ANALYSIS_CACHE

    root = _pkg().get_workspace_root()
    docs_dir = _gh_planner_docs_dir(root)
    cleared: list[str] = []
    errors: list[str] = []

    for cache, name in [
        (_ANALYSIS_CACHE, "_ANALYSIS_CACHE"),
        (_PROJECT_DOCS_CACHE, "_PROJECT_DOCS_CACHE"),
        (_FILE_TREE_CACHE, "_FILE_TREE_CACHE"),
        (_SESSION_HEADER_CACHE, "_SESSION_HEADER_CACHE"),
        (_LABEL_CACHE, "_LABEL_CACHE"),
        (_LABEL_ANALYSIS_CACHE, "_LABEL_ANALYSIS_CACHE"),
    ]:
        if cache:
            cache.clear()
            cleared.append(name)

    for fname in _GH_PLANNER_VOLATILE_FILES:
        p = docs_dir / fname
        if p.exists():
            try:
                p.unlink()
                cleared.append(str(p.relative_to(root)))
            except OSError as exc:
                errors.append(f"{p.name}: {exc}")

    success = len(errors) == 0
    return {
        "success": success,
        "cleared": cleared,
        "errors": errors,
        "_display": (f"🧹 **Cleared:** {', '.join(cleared)}" if cleared else "🧹 Nothing to clear") if success else f"⚠️ **Unload partial** — {len(errors)} error(s): {', '.join(errors)}",
    }


def _do_apply_unload_policy(command: str) -> dict:
    """Clear only the caches listed in unload_policy.json for the given command."""
    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir

    # Import all caches for _CACHE_KEY_MAP
    from extensions.gh_management.github_planner.analysis import _ANALYSIS_CACHE, _FILE_TREE_CACHE
    from extensions.gh_management.github_planner.project_docs import _PROJECT_DOCS_CACHE, _SESSION_HEADER_CACHE
    from extensions.gh_management.github_planner.labels import _LABEL_CACHE, _LABEL_ANALYSIS_CACHE
    from extensions.gh_management.github_planner.milestones import _MILESTONE_CACHE
    from extensions.gh_management.github_planner.setup import _REPO_CACHE
    from extensions.gh_management.github_planner.session import _SESSION_REPO_CONFIRMED
    _p = _pkg()

    root = _p.get_workspace_root()
    if command not in ("init",):
        if err := _p.ensure_initialized(root):
            return err

    _CACHE_KEY_MAP: dict[str, tuple] = {
        "analysis_cache":            (_ANALYSIS_CACHE,          None),
        "project_docs_cache":        (_PROJECT_DOCS_CACHE,      None),
        "file_tree_cache":           (_FILE_TREE_CACHE,          None),
        "session_header_cache":      (_SESSION_HEADER_CACHE,    None),
        "label_cache":               (_LABEL_CACHE,             None),
        "label_analysis_cache":      (_LABEL_ANALYSIS_CACHE,   None),
        "milestone_cache":           (_MILESTONE_CACHE,         None),
        "repo_cache":                (_REPO_CACHE,              None),
        "session_repo_confirmation": (_SESSION_REPO_CONFIRMED,  None),
        "analyzer_snapshot":         (None, "analyzer_snapshot.json"),
        "file_hashes":               (None, "file_hashes.json"),
        "file_tree":                 (None, "file_tree.json"),
        "github_local_config":       (None, "github_local_config.json"),
        "docs_strategy":             (None, "docs_strategy.json"),
        "docs_config":               (None, "docs_config.json"),
    }

    policy = _p._load_unload_policy()
    if "error" in policy:
        return {"error": "policy_load_failed", "message": policy["error"], "_hook": None}

    commands = policy.get("commands", {})
    if command not in commands:
        available = sorted(commands.keys())
        return {
            "error": "unknown_command",
            "message": f"No policy found for command {command!r}. Available: {available}",
            "_hook": None,
        }

    entry = commands[command]
    to_unload: list[str] = entry.get("unload", [])
    to_keep: list[str] = entry.get("keep", [])
    docs_dir = _gh_planner_docs_dir(root)

    cleared: list[str] = []
    errors: list[str] = []

    for key in to_unload:
        if key not in _CACHE_KEY_MAP:
            errors.append(f"Unknown cache key: {key!r}")
            continue
        mem_cache, disk_file = _CACHE_KEY_MAP[key]
        if mem_cache is not None and mem_cache:
            mem_cache.clear()
            cleared.append(key)
        if disk_file is not None:
            p = docs_dir / disk_file
            if p.exists():
                try:
                    p.unlink()
                    cleared.append(disk_file)
                except OSError as exc:
                    errors.append(f"{disk_file}: {exc}")

    success = len(errors) == 0

    cache_descriptions = policy.get("cache_keys", {})
    always_keep = set(policy.get("always_keep", []))

    unloaded_lines = []
    for key in to_unload:
        desc = cache_descriptions.get(key, key)
        if key in cleared:
            unloaded_lines.append(f"  🗑️  {key} — {desc}")
        else:
            unloaded_lines.append(f"  ⚪ {key} — already empty")

    kept_lines = []
    _commands_dir = _p._COMMANDS_DIR
    for key in to_keep:
        if key in always_keep:
            kept_lines.append(f"  🔵 {key} — persistent (never cleared)")
        else:
            desc = cache_descriptions.get(key, key)
            mem_cache, _ = _CACHE_KEY_MAP.get(key, (None, None))
            if mem_cache is not None:
                status = "hot" if mem_cache else "empty"
                kept_lines.append(f"  🟢 {key} — {status}")
            else:
                kept_lines.append(f"  🔵 {key} — {desc}")

    cmd_file = command.replace("/", "/") + ".md"
    cmd_path = _commands_dir / cmd_file
    prompt_line = f"  Prompt: extensions/gh_management/github_planner/commands/{cmd_file}" if cmd_path.exists() else ""

    unloaded_block = "\n".join(unloaded_lines) if unloaded_lines else "  (nothing to clear)"
    kept_block = "\n".join(kept_lines) if kept_lines else "  (none)"
    display = (
        f"Context switch — {command}\n"
        + (f"{prompt_line}\n" if prompt_line else "")
        + f"Unloaded:\n{unloaded_block}\n"
        + f"Kept:\n{kept_block}"
    )
    if errors:
        display += "\nErrors:\n" + "\n".join(f"  ⚠ {e}" for e in errors)

    return {
        "success": success,
        "command": command,
        "cleared": cleared,
        "kept": to_keep,
        "errors": errors,
        "_display": display,
    }


def _do_get_session_header() -> dict:
    """Delegate to project_docs._do_get_session_header for the workspace_tools API."""
    from extensions.gh_management.github_planner.project_docs import _do_get_session_header
    return _do_get_session_header()
