"""Label management — caches, analysis, config helpers, and MCP tool implementations."""
# stdlib
import json
import os
import time
from pathlib import Path


def _pkg():
    """Return the github_planner package module so patches applied by tests are respected."""
    import sys
    return sys.modules['extensions.gh_management.github_planner']

# Label cache — Key: "owner/repo" string, Value: list[{"name", "color", "description"}]
_LABEL_CACHE: dict[str, list[dict]] = {}

# Full label-analysis cache — Key: "owner/repo" string, Value: classified result dict
_LABEL_ANALYSIS_CACHE: dict[str, dict] = {}

_GITHUB_DEFAULT_LABEL_NAMES = frozenset({
    "bug", "documentation", "duplicate", "enhancement", "good first issue",
    "help wanted", "invalid", "question", "wontfix",
})

_LABEL_ACTIVE_DAYS = 30  # labels created within this many days are considered "active"


def _get_cached_label_names(repo: str) -> list[str] | None:
    """Return cached label names for repo, or None if not yet cached."""
    cached = _LABEL_CACHE.get(repo)
    if cached is None:
        return None
    return [lbl["name"] for lbl in cached]


def _normalise_labels(raw_labels: list[dict]) -> list[dict]:
    """Normalise raw GitHub label dicts to {name, color, description} shape."""
    return [
        {"name": lbl.get("name", ""), "color": lbl.get("color", ""), "description": lbl.get("description", "")}
        for lbl in raw_labels
    ]


def _global_config_path(root: Path) -> Path:
    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir
    return root / "hub_agents" / "github_global_config.json"


def _local_config_path(root: Path) -> Path:
    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir
    return _gh_planner_docs_dir(root) / "github_local_config.json"


def _do_analyze_github_labels(refresh: bool = False) -> dict:
    """Fetch labels from GitHub, classify active vs closed, save to github_local_config.json (#81)."""
    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    repo = _p.read_env(root).get("GITHUB_REPO", "")
    # Full analysis cache hit — return immediately without any API call
    if not refresh and repo in _LABEL_ANALYSIS_CACHE:
        return {**_LABEL_ANALYSIS_CACHE[repo], "cached": True}
    _cached_raw: list | None = None
    if not refresh and repo in _LABEL_CACHE:
        _cached_raw = _LABEL_CACHE[repo]

    gh, error_message = _p.get_github_client()
    if gh is None:
        return {"error": "github_unavailable", "message": error_message, "_guidance": _p._G_AUTH}

    with gh:
        try:
            raw_labels = _cached_raw if _cached_raw is not None else gh.list_labels()
            open_issues = gh.list_issues(state="open", per_page=100)
        except Exception as exc:
            return {"error": "github_error", "message": str(exc)}

    # Build set of label names that have open issues
    labels_with_open_issues: set[str] = set()
    for issue in open_issues:
        for lbl in issue.get("labels", []):
            labels_with_open_issues.add(lbl.get("name", ""))

    now_ts = time.time()
    active_labels: list[dict] = []
    closed_labels: list[dict] = []

    for lbl in raw_labels:
        name = lbl.get("name", "")
        created_at_str = lbl.get("created_at", "")
        has_open = name in labels_with_open_issues

        age_days: float | None = None
        if created_at_str:
            try:
                import datetime as _dt
                created_ts = _dt.datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                ).timestamp()
                age_days = (now_ts - created_ts) / 86400
            except (ValueError, OSError):
                age_days = None

        is_recent = age_days is not None and age_days < _LABEL_ACTIVE_DAYS

        entry = {
            "name": name,
            "color": lbl.get("color", ""),
            "description": lbl.get("description", ""),
        }
        if has_open or is_recent:
            active_labels.append(entry)
        else:
            closed_labels.append(entry)

    all_names = {lbl.get("name", "") for lbl in raw_labels}
    only_defaults = bool(raw_labels) and all_names.issubset(_GITHUB_DEFAULT_LABEL_NAMES)

    result: dict = {
        "active_labels": active_labels,
        "closed_labels": closed_labels,
        "total": len(raw_labels),
        "only_defaults": only_defaults,
    }

    docs_dir = _gh_planner_docs_dir(root)
    docs_dir.mkdir(parents=True, exist_ok=True)
    config_path = _local_config_path(root)

    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing["labels"] = {
        "active": active_labels,
        "closed": closed_labels,
        "fetched_at": now_ts,
    }
    tmp = config_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    import os as _os5; _os5.replace(tmp, config_path)

    _LABEL_CACHE[repo] = _normalise_labels(raw_labels)
    _LABEL_ANALYSIS_CACHE[repo] = {
        "active_labels": active_labels,
        "closed_labels": closed_labels,
        "total": len(raw_labels),
        "only_defaults": only_defaults,
    }

    n_active = len(active_labels)
    n_closed = len(closed_labels)
    result["_display"] = (
        f"✓ Labels analyzed: {n_active} active, {n_closed} inactive\n"
        f"  Saved to hub_agents/extensions/gh_planner/github_local_config.json"
    )
    if only_defaults:
        result["suggestion"] = (
            "Only GitHub default labels found. Consider adding project-specific labels "
            "based on your feature areas. Call analyze_github_labels again after creating them."
        )
    return result


def _do_load_github_local_config() -> dict:
    """Load github_local_config.json from disk, or return empty config (#81)."""
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    config_path = _local_config_path(root)
    if not config_path.exists():
        return {"labels": None, "fetched_at": None}

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        labels_section = data.get("labels", {})
        return {
            "labels": {
                "active": labels_section.get("active", []),
                "closed": labels_section.get("closed", []),
            },
            "fetched_at": labels_section.get("fetched_at"),
        }
    except (json.JSONDecodeError, OSError):
        return {"labels": None, "fetched_at": None}


_GLOBAL_CONFIG_DEFAULTS: dict = {
    "auth": {"method": "none", "username": None},
    "default_repo": None,
    "rate_limit_remaining": None,
    "last_checked": None,
}


def _do_load_github_global_config() -> dict:
    """Load hub_agents/github_global_config.json — creates with defaults if absent (#80)."""
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    path = _global_config_path(root)
    if not path.exists():
        token, source = _p.resolve_token()
        defaults = {**_GLOBAL_CONFIG_DEFAULTS}
        if token:
            defaults["auth"] = {"method": source.value, "username": None}
        env = _p.read_env(root)
        if repo := env.get("GITHUB_REPO"):
            defaults["default_repo"] = repo
        defaults["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
        import os as _os6; _os6.replace(tmp, path)
        return {**defaults, "created": True}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {**_GLOBAL_CONFIG_DEFAULTS}


def _do_save_github_local_config(data: dict) -> dict:
    """Merge data into hub_agents/extensions/gh_planner/github_local_config.json (#80)."""
    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    docs_dir = _gh_planner_docs_dir(root)
    docs_dir.mkdir(parents=True, exist_ok=True)
    config_path = _local_config_path(root)

    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing.update(data)
    tmp = config_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    import os as _os7; _os7.replace(tmp, config_path)

    return {
        "saved": True,
        "file": str(config_path.relative_to(root)),
        "_display": f"✓ Local config saved to {config_path.relative_to(root)}",
    }


def _do_get_github_config(scope: str = "both") -> dict:
    """Return GitHub config for scope: 'global', 'local', or 'both' (#80)."""
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    valid = {"global", "local", "both"}
    if scope not in valid:
        return {"error": "invalid_scope", "message": f"scope must be one of {sorted(valid)}"}

    result: dict = {"scope": scope}

    if scope in ("global", "both"):
        result["global"] = _do_load_github_global_config()

    if scope in ("local", "both"):
        result["local"] = _do_load_github_local_config()

    return result


def _do_list_repo_labels() -> dict:
    """Fetch labels from GitHub and cache them."""
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    repo = _p.read_env(root).get("GITHUB_REPO", "")

    if repo in _LABEL_CACHE:
        labels = _LABEL_CACHE[repo]
        names = [lbl["name"] for lbl in labels]
        display_lines = "\n".join(f"  • {lbl['name']} — {lbl.get('description', '')}" for lbl in labels)
        return {
            "labels": labels, "names": names, "count": len(labels), "cached": True,
            "_display": f"{len(labels)} labels on {repo} [cached]:\n{display_lines}",
        }

    gh, err = _p.get_github_client()
    if gh is None:
        return err
    try:
        with gh:
            raw = gh.list_labels()
        labels = _normalise_labels(raw)
        _LABEL_CACHE[repo] = labels
        names = [l["name"] for l in labels]
        display_lines = "\n".join(f"  • {l['name']} — {l.get('description', '')}" for l in labels)
        return {
            "labels": labels,
            "names": names,
            "count": len(labels),
            "_display": f"{len(labels)} labels on {repo}:\n{display_lines}",
        }
    except Exception as exc:
        return {"error": "list_labels_failed", "message": str(exc)}


def _do_make_label(name: str, color: str, description: str = "") -> dict:
    """Create a label on GitHub (idempotent). Updates the label cache."""
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    if not name:
        return {"error": "missing_field", "message": "name is required"}
    gh, err = _p.get_github_client()
    if gh is None:
        return err
    repo = _p.read_env(root).get("GITHUB_REPO", "")
    try:
        with gh:
            label = gh.create_label(name, color, description)
        _LABEL_CACHE.pop(repo, None)
        _LABEL_ANALYSIS_CACHE.pop(repo, None)
        return {
            "name": label["name"],
            "color": label["color"],
            "description": label.get("description", ""),
            "_display": f"✅ **Label ready:** `{name}` on {repo}",
        }
    except Exception as exc:
        return {"error": "make_label_failed", "message": str(exc)}
