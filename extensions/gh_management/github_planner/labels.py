"""Label management — caches, analysis, config helpers, and MCP tool implementations."""
# stdlib
import datetime as _dt
import json
import os
import time
from pathlib import Path


from extensions.gh_management.github_planner.pkgref import _pkg, _resolve_root

# Label cache — Key: "owner/repo" string, Value: list[{"name", "color", "description"}]
_LABEL_CACHE: dict[str, list[dict]] = {}

# Full label-analysis cache — Key: "owner/repo" string, Value: classified result dict
_LABEL_ANALYSIS_CACHE: dict[str, dict] = {}

_GITHUB_DEFAULT_LABEL_NAMES = frozenset({
    "bug", "documentation", "duplicate", "enhancement", "good first issue",
    "help wanted", "invalid", "question", "wontfix",
})

_LABEL_ACTIVE_DAYS = 30  # labels created within this many days are considered "active"


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


def _label_names_with_open_issues(open_issues: list[dict]) -> set[str]:
    """Names of every label carried by at least one open issue."""
    return {
        lbl.get("name", "")
        for issue in open_issues
        for lbl in issue.get("labels", [])
    }


def _label_age_days(created_at_str: str, now_ts: float) -> float | None:
    """Age of a label in days, or None when GitHub sent no parseable timestamp."""
    if not created_at_str:
        return None
    try:
        created_ts = _dt.datetime.fromisoformat(
            created_at_str.replace("Z", "+00:00")
        ).timestamp()
    except (ValueError, OSError):
        return None
    return (now_ts - created_ts) / 86400


def _classify_labels(
    raw_labels: list[dict], open_issue_label_names: set[str], now_ts: float
) -> tuple[list[dict], list[dict]]:
    """Split labels into (active, closed).

    A label is active when it carries an open issue or was created within
    _LABEL_ACTIVE_DAYS. Everything else is closed.
    """
    active: list[dict] = []
    closed: list[dict] = []
    for lbl in raw_labels:
        name = lbl.get("name", "")
        age_days = _label_age_days(lbl.get("created_at", ""), now_ts)
        is_recent = age_days is not None and age_days < _LABEL_ACTIVE_DAYS
        entry = {
            "name": name,
            "color": lbl.get("color", ""),
            "description": lbl.get("description", ""),
        }
        (active if name in open_issue_label_names or is_recent else closed).append(entry)
    return active, closed


def _persist_label_analysis(root, active_labels, closed_labels, now_ts) -> None:
    """Merge the label section into github_local_config.json, atomically."""
    from extensions.gh_management.github_planner.project_docs import _gh_planner_docs_dir

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
    os.replace(tmp, config_path)


def _do_analyze_github_labels(refresh: bool = False) -> dict:
    """Fetch labels from GitHub, classify active vs closed, save to github_local_config.json (#81)."""
    _p = _pkg()

    root, err = _resolve_root()
    if err:
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

    now_ts = time.time()
    active_labels, closed_labels = _classify_labels(
        raw_labels, _label_names_with_open_issues(open_issues), now_ts
    )

    all_names = {lbl.get("name", "") for lbl in raw_labels}
    only_defaults = bool(raw_labels) and all_names.issubset(_GITHUB_DEFAULT_LABEL_NAMES)

    result: dict = {
        "active_labels": active_labels,
        "closed_labels": closed_labels,
        "total": len(raw_labels),
        "only_defaults": only_defaults,
    }

    _persist_label_analysis(root, active_labels, closed_labels, now_ts)

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
    root, err = _resolve_root()
    if err:
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

    root, err = _resolve_root()
    if err:
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
    root, err = _resolve_root()
    if err:
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
    root, err = _resolve_root()
    if err:
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

    root, err = _resolve_root()
    if err:
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

    root, err = _resolve_root()
    if err:
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


def register_label_tools(mcp) -> None:
    """Register the label and GitHub-config MCP tools."""
    @mcp.tool()
    def analyze_github_labels(refresh: bool = False) -> dict:
        """Fetch and classify GitHub labels for the configured repo (#81).

        Classifies labels as:
          active_labels  — labels with open issues OR created < 30 days ago
          closed_labels  — labels with no open issues AND created > 30 days ago

        Results saved to hub_agents/extensions/gh_planner/github_local_config.json.
        Use active_labels when suggesting labels for new issues via draft_issue.

        If only GitHub default labels exist, returns suggestion for project-specific labels.
        Set refresh=True to bypass the in-memory cache and re-fetch from GitHub.
        """
        return _do_analyze_github_labels(refresh)


    @mcp.tool()
    def load_github_local_config() -> dict:
        """Read the saved github_local_config.json from disk (#81).

        Returns {labels: {active: [...], closed: [...]}, fetched_at: float | null}.
        Call analyze_github_labels first to populate this file.
        """
        return _do_load_github_local_config()


    @mcp.tool()
    def load_github_global_config() -> dict:
        """Read or create hub_agents/github_global_config.json (#80).

        Stores auth method, username, default_repo, and rate-limit metadata.
        Never stores tokens. Never cleared by unload_plugin (persists across sessions).
        Returns {auth: {method, username}, default_repo, rate_limit_remaining, last_checked}.
        """
        return _do_load_github_global_config()


    @mcp.tool()
    def save_github_local_config(data: dict) -> dict:
        """Merge data into hub_agents/extensions/gh_planner/github_local_config.json (#80).

        Shallow merge: top-level keys from data overwrite existing values.
        Atomic write. Use for storing repo-specific fields like default_branch, issue_templates.
        """
        return _do_save_github_local_config(data)


    @mcp.tool()
    def get_github_config(scope: str = "both") -> dict:
        """Return GitHub config for scope: 'global', 'local', or 'both' (#80).

        global: auth method, default_repo, rate-limit metadata.
        local:  project-specific labels, templates, etc.
        both:   merged view with both sections (default).

        Load only what you need — global is ~20 tokens, local is ~50 tokens.
        """
        return _do_get_github_config(scope)


    @mcp.tool()
    def list_repo_labels() -> dict:
        """Fetch all labels from the GitHub repo and cache them locally.

        Call before draft_issue to know which labels are available.
        Returns {labels, names, count}. Returns from cache if available."""
        return _do_list_repo_labels()


    @mcp.tool()
    def make_label(name: str, color: str, description: str = "") -> dict:
        """Create a GitHub label (idempotent — returns existing if already present).

        Follow the conventional palette:
          bug=#d73a4a, enhancement=#a2eeef, feature=#0075ca,
          documentation=#0075ca, refactor=#e4e669, performance=#e4e669,
          chore=#ededed, test=#bfd4f2, priority:high=#e11d48,
          priority:low=#86efac, status:needs-triage=#fbbf24

        color: hex color WITHOUT the # prefix (e.g. 'd73a4a')
        """
        return _do_make_label(name, color, description)
