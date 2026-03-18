"""GitHub Planner plugin for terminal-hub.

Registers all GitHub-specific MCP tools and resources.
Call register(mcp) from create_server() to activate.
"""
import ast
import hashlib
import json
import os
import re
import time
from datetime import date
from pathlib import Path

from extensions.github_planner.storage import (
    IssueStatus,
    list_issue_files,
    next_local_number,
    read_doc_file,
    read_issue_file,
    read_issue_frontmatter,
    resolve_slug,
    update_issue_status,
    validate_slug,
    write_doc_file,
    write_issue_file,
)
from extensions.github_planner.client import GitHubClient, GitHubError, create_user_repo, load_default_labels
from extensions.github_planner.auth import get_auth_options, resolve_token, verify_gh_cli_auth
from terminal_hub.config import read_preference, write_preference
from terminal_hub.env_store import read_env
from terminal_hub.errors import msg
from terminal_hub.slugify import slugify
from terminal_hub.workspace import detect_repo, resolve_workspace_root

_PLUGIN_DIR = Path(__file__).parent
_COMMANDS_DIR = _PLUGIN_DIR / "commands"

# ── Runtime caches (session-scoped, cleared on server restart) ─────────────────
# Key: "owner/repo"
_ANALYSIS_CACHE: dict[str, dict] = {}
# {
#   "pending_md":   [{"path": str, "size": int}, ...],
#   "pending_code": [{"path": str, "size": int}, ...],
#   "analyzed":     [{"path": str, "is_markdown": bool}],
#   "skipped":      [{"path": str, "reason": str}],
#   "repo":         str,
#   "started_at":   float,
#   "last_fetched": float | None,
# }

_PROJECT_DOCS_CACHE: dict[str, dict] = {}
# Key: "owner/repo"
# {
#   "summary":    str | None,
#   "detail":     str | None,
#   "_sections":  dict[str, str] | None,  # parsed H2 sections of detail
#   "loaded_at":  float,
# }

_FILE_TREE_CACHE: dict = {}
# {
#   "tree":       dict,     # nested dir structure
#   "flat_index": list[str],
#   "fetched_at": str,      # ISO timestamp
#   "root":       str,
# }

_FILE_TREE_TTL = 3600  # seconds

_FILE_TREE_IGNORE = frozenset({
    ".git", "__pycache__", "venv", ".venv", "node_modules",
    ".worktrees", "worktrees", ".mypy_cache", ".pytest_cache",
    "dist", "build", "*.egg-info",
})

# ── Guidance URIs ─────────────────────────────────────────────────────────────
_G_INIT    = "terminal-hub://workflow/init"
_G_ISSUE   = "terminal-hub://workflow/issue"
_G_CONTEXT = "terminal-hub://workflow/context"
_G_AUTH    = "terminal-hub://workflow/auth"

_BUILTIN_COMMANDS = ["create.md", "github-planner/setup.md", "github-planner/auth.md", "context.md"]


def _load_agent(name: str) -> str:
    path = _COMMANDS_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def get_workspace_root() -> Path:
    return resolve_workspace_root()


def ensure_initialized(root: Path) -> dict | None:
    """Return a needs_init response if hub_agents/ is absent, else None."""
    if not (root / "hub_agents").exists():
        return {
            "status": "needs_init",
            "message": (
                "This project hasn't been set up with terminal-hub yet. "
                "Ask the user: would they like GitHub integration? If yes, what is their repo (owner/repo format)? "
                "Then call setup_workspace to initialise."
            ),
            "_guidance": _G_INIT,
        }
    return None


def get_github_client() -> tuple[GitHubClient | None, str]:
    """Return (client, error_message). Client is None if auth unavailable."""
    token, source = resolve_token()
    if token is None:
        return None, source.suggestion()

    root = get_workspace_root()
    root_key = str(root)
    # Cache detect_repo per root — avoids re-reading hub_agents/.env on every call (#90)
    if root_key not in _REPO_CACHE:
        _REPO_CACHE[root_key] = detect_repo(root)
    repo = _REPO_CACHE[root_key]
    if not repo:
        return None, (
            "No GitHub repo configured for this project. "
            "Call setup_workspace with github_repo='owner/repo' to set one."
        )

    return GitHubClient(token=token, repo=repo), ""


# Per-root repo string cache — avoids re-reading hub_agents/.env on every call (#90)
_REPO_CACHE: dict[str, str | None] = {}


def _invalidate_repo_cache() -> None:
    """Clear repo cache. Call after setup_workspace changes the env."""
    _REPO_CACHE.clear()


# Per-root label analysis cache — avoids re-fetching on every call (#81)
# Key: str(root), Value: {active_labels, closed_labels, fetched_at}
_LABEL_CACHE: dict[str, dict] = {}

_GITHUB_DEFAULT_LABEL_NAMES = frozenset({
    "bug", "documentation", "duplicate", "enhancement", "good first issue",
    "help wanted", "invalid", "question", "wontfix",
})

_LABEL_ACTIVE_DAYS = 30  # labels created within this many days are considered "active"


def _global_config_path(root: Path) -> Path:
    return root / "hub_agents" / "github_global_config.json"


def _local_config_path(root: Path) -> Path:
    return _gh_planner_docs_dir(root) / "github_local_config.json"


# ── Internal alias for analyzer ───────────────────────────────────────────────
_get_github_client = get_github_client

# ── Tool implementations ──────────────────────────────────────────────────────

def _do_check_auth() -> dict:
    token, source = resolve_token()
    if token:
        return {
            "authenticated": True,
            "source": source.value,
            "message": f"Authenticated via {source.value.replace('_', ' ')}.",
        }
    return {
        "authenticated": False,
        "message": "No GitHub authentication found.",
        "options": get_auth_options(),
        "_guidance": _G_AUTH,
    }


def _do_verify_auth() -> dict:
    success, message = verify_gh_cli_auth()
    if success:
        return {"authenticated": True, "source": "gh_cli", "message": message}
    return {
        "authenticated": False,
        "message": message,
        "options": get_auth_options(),
        "_guidance": _G_AUTH,
    }


def _do_generate_issue_workflows(slug: str) -> dict:
    """Append agent + program workflow scaffolding to an existing issue file (#88).

    Reads the issue's title, body, and labels, then writes a structured workflow
    section that Claude can fill in during implementation.
    """
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    fm = read_issue_frontmatter(root, slug)
    if not fm:
        return {"error": "issue_not_found", "message": f"No issue found for slug {slug!r}"}

    title = fm.get("title", slug)
    labels: list[str] = fm.get("labels") or []

    # Infer change type from labels
    if any("bug" in lbl.lower() for lbl in labels):
        change_type = "bug fix"
    elif any(lbl in ("enhancement", "feature") for lbl in labels):
        change_type = "feature"
    elif any("refactor" in lbl.lower() for lbl in labels):
        change_type = "refactor"
    elif any("test" in lbl.lower() for lbl in labels):
        change_type = "test"
    elif any("doc" in lbl.lower() for lbl in labels):
        change_type = "documentation"
    else:
        change_type = "implementation"

    workflow_steps = [
        "orient: re-read issue, identify affected files",
        "plan: list changes, confirm approach fits codebase patterns",
        "implement: atomic, test-verified changes",
        "verify: all tests pass, coverage ≥ 80%, acceptance criteria met",
    ]

    agent_workflow_text = (
        f"Orient → read issue #{slug} carefully. "
        f"Change type: {change_type}. "
        "Plan minimal file changes, implement with test verification after each step, "
        "verify full suite passes before marking done."
    )

    workflow_body_section = f"""
---

## Agent Workflow

### 1. Orient
- Re-read this issue (Issue #{slug}) title and body carefully
- Identify the minimal set of files affected
- Understand the acceptance criteria before touching any code

### 2. Plan
- List files to change; prefer editing existing over creating new
- Confirm the approach fits existing patterns in the codebase

### 3. Implement
- Make atomic, test-verified changes
- Run `python -m pytest` after each logical change

### 4. Verify
- All tests pass
- Coverage ≥ 80%
- Acceptance criteria met

---

## Program Workflow

**Change type:** {change_type}

### Affected components
<!-- Fill in: list files/modules that need to change -->

### Test plan
- [ ] Unit tests for new/changed logic
- [ ] Update existing tests if behaviour changed
- [ ] No regressions (full suite passes)
"""

    # Append to the issue file body (after existing content)
    issue_path = root / "hub_agents" / "issues" / f"{slug}.md"
    if not issue_path.exists():
        return {"error": "issue_not_found", "message": f"File missing: {issue_path}"}

    existing = issue_path.read_text(encoding="utf-8")
    if "## Agent Workflow" in existing:
        return {"slug": slug, "updated": False, "message": "Workflow section already present"}

    # Update front-matter with workflow + agent_workflow fields if not set
    # (Files without front matter can't reach here — read_issue_frontmatter returns None first)
    import yaml as _yaml
    parts = existing.split("---", 2)
    raw_fm = _yaml.safe_load(parts[1]) or {}
    body_rest = parts[2] if len(parts) > 2 else ""
    if not raw_fm.get("workflow"):
        raw_fm["workflow"] = workflow_steps
    if not raw_fm.get("agent_workflow"):
        raw_fm["agent_workflow"] = agent_workflow_text
    updated_front = f"---\n{_yaml.dump(raw_fm, default_flow_style=False)}---\n{body_rest}"
    import os as _os
    tmp = issue_path.with_suffix(".tmp")
    tmp.write_text(updated_front.rstrip() + workflow_body_section, encoding="utf-8")
    _os.replace(tmp, issue_path)

    return {
        "slug": slug,
        "updated": True,
        "file": f"hub_agents/issues/{slug}.md",
        "_display": f"✓ Workflow scaffold added to #{slug}",
    }


def _do_draft_issue(
    title: str,
    body: str,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    note: str | None = None,
) -> dict:
    """Save an issue draft locally as status=pending."""
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    if not title:
        return {"error": "draft_failed", "message": msg("missing_field", detail="title"), "_hook": None}
    if not body:
        return {"error": "draft_failed", "message": msg("missing_field", detail="body"), "_hook": None}

    labels = labels or []
    assignees = assignees or []

    slug = next_local_number(root)

    try:
        write_issue_file(
            root=root,
            slug=slug,
            title=title,
            body=body,
            assignees=assignees,
            labels=labels,
            created_at=date.today(),
            status=IssueStatus.PENDING,
            note=note,
        )
    except OSError as exc:
        return {"error": "draft_failed", "message": msg("draft_failed", detail=str(exc)), "_hook": None}

    display = f"✓ {title}"
    return {
        "slug": slug,
        "title": title,
        "preview_body": body[:300] + ("…" if len(body) > 300 else ""),
        "labels": labels,
        "assignees": assignees,
        "status": str(IssueStatus.PENDING),
        "local_file": f"hub_agents/issues/{slug}.md",
        "_display": display,
    }


def _do_submit_issue(slug: str) -> dict:
    """Submit a pending local issue draft to GitHub."""
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    try:
        validate_slug(slug)
    except ValueError:
        return {"error": "submit_failed", "message": msg("not_found", detail=slug), "_hook": None}

    fm = read_issue_frontmatter(root, slug)
    if fm is None:
        return {"error": "submit_failed", "message": msg("not_found", detail=slug), "_hook": None}

    # #59 — idempotency guard: refuse to re-submit already-submitted issues
    current_status = str(fm.get("status", "")).lower()
    if current_status == str(IssueStatus.OPEN):
        return {
            "error": "already_submitted",
            "message": f"Issue '{slug}' is already open on GitHub.",
            "issue_number": fm.get("issue_number"),
            "url": fm.get("github_url"),
            "_hook": None,
        }
    if current_status == str(IssueStatus.CLOSED):
        return {
            "error": "already_closed",
            "message": f"Issue '{slug}' is closed and cannot be re-submitted.",
            "_hook": None,
        }

    gh, error_message = get_github_client()
    if gh is None:
        return {
            "error": "github_unavailable",
            "message": error_message,
            "_guidance": _G_AUTH,
            "_hook": None,
        }

    labels: list[str] = fm.get("labels") or []
    raw = read_issue_file(root, slug) or ""
    body = raw.split("---", 2)[-1].strip() if raw.startswith("---") else raw

    with gh:
        if labels:
            label_err = gh.ensure_labels(labels)
            if label_err:
                return {"error": "label_bootstrap_failed", "message": label_err, "_hook": None}

        try:
            result = gh.create_issue(
                title=fm["title"],
                body=body,
                labels=labels,
                assignees=fm.get("assignees") or [],
            )
        except GitHubError as exc:
            return {**exc.to_dict(), "_hook": None}

    update_issue_status(
        root, slug,
        status=IssueStatus.OPEN,
        issue_number=result["number"],
        github_url=result["html_url"],
    )

    result_dict = {
        "issue_number": result["number"],
        "url": result["html_url"],
        "slug": slug,
        "local_file": f"hub_agents/issues/{slug}.md",
    }
    return {**result_dict, "_display": f"✓ #{result['number']} {fm['title']}"}


def _do_get_issue_context(slug: str) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    try:
        validate_slug(slug)
    except ValueError:
        return {"error": "not_found", "message": msg("not_found", detail=slug), "_hook": None}

    content = read_issue_file(root, slug)
    if content is None:
        return {"error": "not_found", "message": msg("not_found", detail=slug), "_hook": None}
    return {"slug": slug, "content": content}


_ALLOWED_PREFERENCES = {"confirm_arch_changes", "github_repo_connected"}


def _do_set_preference(key: str, value: bool) -> dict:
    """Persist a user preference in hub_agents/config.yaml."""
    root = get_workspace_root()
    if err := ensure_initialized(root):
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
    from terminal_hub.workspace import resolve_workspace_root
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    token, source = resolve_token()
    if token is None:
        return {
            "error": "github_unavailable",
            "message": source.suggestion(),
            "_guidance": _G_AUTH,
            "_hook": None,
        }

    try:
        data = create_user_repo(token=token, name=name, description=description, private=private)
    except GitHubError as exc:
        return {"error": exc.error_code, "message": str(exc), "_hook": None}

    full_name = data.get("full_name", f"unknown/{name}")
    html_url = data.get("html_url", "")

    # Persist the new repo in workspace config
    from terminal_hub.config import save_config, WorkspaceMode
    from terminal_hub.env_store import write_env as _write_env
    _write_env(root, {"GITHUB_REPO": full_name})
    save_config(root, WorkspaceMode.GITHUB, full_name)
    write_preference(root, "github_repo_connected", True)
    _invalidate_repo_cache()

    return {
        "success": True,
        "github_repo": full_name,
        "url": html_url,
        "private": private,
        "_display": f"✓ GitHub repo created: {full_name} ({'private' if private else 'public'})",
    }


def _do_update_project_description(content: str) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    try:
        path = write_doc_file(root, "project_description", content)
        return {"updated": True, "file": str(path.relative_to(root)), "_display": "✓ Project description saved"}
    except (OSError, ValueError) as exc:
        return {"error": "write_failed", "message": msg("write_failed", detail=str(exc)), "_hook": None}


def _do_update_architecture(content: str) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    try:
        path = write_doc_file(root, "architecture", content)
        return {"updated": True, "file": str(path.relative_to(root)), "_display": "✓ Architecture notes saved"}
    except (OSError, ValueError) as exc:
        return {"error": "write_failed", "message": msg("write_failed", detail=str(exc)), "_hook": None}


def _do_update_project_detail_section(feature_name: str, content: str) -> dict:
    """Merge a single H2 section into project_detail.md without rewriting the full file (#65).

    If a section matching `## {feature_name}` already exists, replaces it.
    Otherwise appends a new section at the end.
    """
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    if not feature_name or not feature_name.strip():
        return {"error": "invalid_input", "message": "feature_name must be non-empty"}
    if not content or not content.strip():
        return {"error": "invalid_input", "message": "content must be non-empty"}

    docs_dir = _gh_planner_docs_dir(root)
    detail_path = docs_dir / "project_detail.md"
    detail_path.parent.mkdir(parents=True, exist_ok=True)

    section_heading = f"## {feature_name.strip()}"
    new_section = f"{section_heading}\n\n{content.strip()}\n"

    if not detail_path.exists():
        tmp = detail_path.with_suffix(".tmp")
        tmp.write_text(new_section, encoding="utf-8")
        import os as _os2; _os2.replace(tmp, detail_path)
        # Invalidate cache so next load_project_docs sees fresh data
        _PROJECT_DOCS_CACHE.pop(str(root), None)
        return {"updated": True, "action": "created", "feature": feature_name,
                "file": str(detail_path.relative_to(root))}

    existing = detail_path.read_text(encoding="utf-8")

    # Find existing section by heading (case-insensitive match)
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
        # Replace existing section
        before = lines[:start_idx]
        after = lines[end_idx:] if end_idx is not None else []
        new_content = "".join(before) + new_section + ("" if not after else "\n" + "".join(after))
        action = "replaced"
    else:
        # Append new section
        new_content = existing.rstrip() + "\n\n" + new_section
        action = "appended"

    import os as _os3
    tmp = detail_path.with_suffix(".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    _os3.replace(tmp, detail_path)

    # Invalidate cache
    _PROJECT_DOCS_CACHE.pop(str(root), None)

    return {"updated": True, "action": action, "feature": feature_name,
            "file": str(detail_path.relative_to(root)),
            "_display": f"✓ Section '{feature_name}' {action} in project_detail.md"}


def _do_get_project_context(doc_key: str) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    # Route through _do_load_project_docs to benefit from _PROJECT_DOCS_CACHE
    if doc_key == "all":
        loaded = _do_load_project_docs(doc="all")
        return {
            "project_description": loaded.get("summary"),
            "architecture": loaded.get("detail"),
        }
    # Legacy single-key access: map old keys to new doc names
    _KEY_MAP = {"project_description": "summary", "architecture": "detail",
                "summary": "summary", "detail": "detail"}
    mapped = _KEY_MAP.get(doc_key)
    if mapped is None:
        return {"error": "not_found", "message": f"Unknown doc key: {doc_key!r}", "_hook": None}
    loaded = _do_load_project_docs(doc=mapped)
    content = loaded.get(mapped)
    return {"doc_key": doc_key, "content": content}


def _do_run_analyzer() -> dict:
    from extensions.github_planner.analyzer import (
        process_snapshot, write_snapshot, summarize_for_prompt, snapshot_age_hours, load_snapshot
    )
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    gh, error_message = _get_github_client()
    if gh is None:
        return {"error": "github_unavailable", "message": error_message, "_guidance": _G_AUTH}

    env = read_env(root)
    repo = env.get("GITHUB_REPO", "unknown")

    with gh:
        try:
            issues = gh.list_issues(state="all", per_page=50)
            labels = gh.list_labels()
            members = gh.list_collaborators()
        except Exception as exc:
            return {"error": "github_error", "message": str(exc)}

    snapshot = process_snapshot(issues, labels, members, repo=repo)
    path = write_snapshot(root, snapshot)
    summary = summarize_for_prompt(snapshot)

    n_issues = snapshot["issues"]["total_sampled"]
    n_open = snapshot["issues"]["total_open"]
    n_labels = len(snapshot["labels"])
    n_members = len(snapshot["members"])
    member_names = ", ".join(m["login"] for m in snapshot["members"][:3])

    display = (
        f"✓ Analyzer complete — {repo}\n"
        f"  Issues sampled : {n_issues} ({n_open} open)\n"
        f"  Labels found   : {n_labels}\n"
        f"  Team members   : {n_members}"
        + (f" ({member_names})" if member_names else "") + "\n"
        f"  Snapshot saved : hub_agents/analyzer_snapshot.json"
    )
    if summary:
        display += f"\n\n  {summary}"

    return {
        "snapshot_file": str(path.relative_to(root)),
        "summary": summary,
        "_display": display,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

_MD_EXTENSIONS = {".md", ".rst", ".txt"}
_MAX_ANALYSIS_FILES = 200
_BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".pdf", ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin",
    ".pkl", ".npy", ".npz", ".db", ".sqlite", ".sqlite3",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".whl", ".egg",
    ".ttf", ".otf", ".woff", ".woff2",
    ".mp3", ".mp4", ".wav", ".ogg", ".mov", ".avi",
})


def _is_markdown(path: str) -> bool:
    return Path(path).suffix.lower() in _MD_EXTENSIONS


def _gh_planner_docs_dir(root: Path) -> Path:
    return root / "hub_agents" / "extensions" / "gh_planner"


def _resolve_repo(repo: str | None) -> str | None:
    """Return explicit repo or fall back to env / single cached entry.

    Cache heuristic is guarded: only returns a cached key if it matches the
    current workspace env (prevents cross-plugin contamination, #103).
    """
    if repo:
        return repo
    root = get_workspace_root()
    env = read_env(root)
    env_repo = env.get("GITHUB_REPO")
    # Use cache only if the single entry matches the current workspace repo (#103)
    if len(_ANALYSIS_CACHE) == 1:
        cached_repo = next(iter(_ANALYSIS_CACHE))
        if env_repo and cached_repo == env_repo:
            return cached_repo
    return env_repo


# ── Repo analysis tools ────────────────────────────────────────────────────────

def _do_start_repo_analysis(repo: str | None = None) -> dict:
    resolved = _resolve_repo(repo)
    if not resolved:
        return {"error": "repo_required", "message": "Pass repo='owner/repo' or configure via setup_workspace.", "_hook": None}

    gh, err = _get_github_client()
    if gh is None:
        return {"error": "github_unavailable", "message": err, "_guidance": _G_AUTH}

    try:
        with gh:
            tree = gh.list_repo_tree()
    except Exception as exc:
        return {"error": "github_error", "message": str(exc), "_hook": None}

    # Cap and partition
    tree = tree[:_MAX_ANALYSIS_FILES]
    md_files = [f for f in tree if _is_markdown(f["path"])]
    code_files = [f for f in tree if not _is_markdown(f["path"])]
    # Sort code files smallest-first to front-load quick reads
    code_files.sort(key=lambda f: f["size"])

    _ANALYSIS_CACHE[resolved] = {
        "pending_md": md_files,
        "pending_code": code_files,
        "analyzed": [],
        "skipped": [],
        "repo": resolved,
        "started_at": time.time(),
        "last_fetched": None,
    }

    return {
        "repo": resolved,
        "total_files": len(tree),
        "md_count": len(md_files),
        "code_count": len(code_files),
        "status": "ready",
        "_display": f"✓ Analysis started — {resolved} ({len(tree)} files: {len(md_files)} docs, {len(code_files)} code)",
    }


def _do_fetch_analysis_batch(repo: str | None = None, batch_size: int = 5) -> dict:
    resolved = _resolve_repo(repo)
    if not resolved or resolved not in _ANALYSIS_CACHE:
        return {"error": "analysis_not_started", "message": "Call start_repo_analysis first.", "_hook": None}

    state = _ANALYSIS_CACHE[resolved]
    batch_size = max(1, min(batch_size, 20))

    gh, err = _get_github_client()
    if gh is None:
        return {"error": "github_unavailable", "message": err, "_guidance": _G_AUTH}

    # Draw from MD queue first, then code
    queue = state["pending_md"] if state["pending_md"] else state["pending_code"]
    to_fetch = queue[:batch_size]

    files_out: list[dict] = []
    with gh:
        for file_meta in to_fetch:
            path = file_meta["path"]
            is_md = _is_markdown(path)
            try:
                content = gh.get_file_content(path)
                files_out.append({"path": path, "content": content, "is_markdown": is_md})
                state["analyzed"].append({"path": path, "is_markdown": is_md})
            except Exception as exc:
                from extensions.github_planner.client import GitHubError
                reason = getattr(exc, "error_code", "unknown")
                state["skipped"].append({"path": path, "reason": reason})

            # Remove from whichever queue it came from
            if is_md and file_meta in state["pending_md"]:
                state["pending_md"].remove(file_meta)
            elif file_meta in state["pending_code"]:
                state["pending_code"].remove(file_meta)

    state["last_fetched"] = time.time()
    remaining = len(state["pending_md"]) + len(state["pending_code"])
    done = remaining == 0

    return {
        "repo": resolved,
        "files": files_out,
        "analyzed_count": len(state["analyzed"]),
        "remaining_count": remaining,
        "done": done,
    }


def _do_get_analysis_status(repo: str | None = None) -> dict:
    resolved = _resolve_repo(repo)
    if not resolved or resolved not in _ANALYSIS_CACHE:
        return {"error": "analysis_not_started", "message": "Call start_repo_analysis first.", "_hook": None}

    state = _ANALYSIS_CACHE[resolved]
    remaining = len(state["pending_md"]) + len(state["pending_code"])
    return {
        "repo": resolved,
        "analyzed_count": len(state["analyzed"]),
        "remaining_count": remaining,
        "skipped_count": len(state["skipped"]),
        "analyzed_paths": [f["path"] for f in state["analyzed"]],
        "remaining_paths": [f["path"] for f in state["pending_md"] + state["pending_code"]],
        "done": remaining == 0,
    }


# ── Project docs tools ────────────────────────────────────────────────────────

def _do_save_project_docs(summary_md: str, detail_md: str, repo: str | None = None) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    docs_dir = _gh_planner_docs_dir(root)
    docs_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in (("project_summary.md", summary_md), ("project_detail.md", detail_md)):
        dest = docs_dir / filename
        tmp = dest.with_suffix(".tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, dest)
        except OSError as exc:
            return {"error": "write_failed", "message": str(exc), "_hook": None}

    resolved = _resolve_repo(repo) or "unknown"
    # Reset docs cache with fresh content (sections re-parsed on next lookup call)
    _PROJECT_DOCS_CACHE[resolved] = {
        "summary": summary_md,
        "detail": detail_md,
        "_sections": None,
        "loaded_at": time.time(),
    }
    # Analysis data is now superseded by written docs — free the memory
    _ANALYSIS_CACHE.pop(resolved, None)
    # Invalidate session header for this root only (#61, #94)
    _SESSION_HEADER_CACHE.pop(str(root), None)

    return {
        "saved": True,
        "summary_path": str((docs_dir / "project_summary.md").relative_to(root)),
        "detail_path": str((docs_dir / "project_detail.md").relative_to(root)),
        "_display": "✓ Project docs saved",
    }


def _do_load_project_docs(doc: str = "summary", repo: str | None = None, force_reload: bool = False) -> dict:
    resolved = _resolve_repo(repo) or "unknown"
    cached = _PROJECT_DOCS_CACHE.get(resolved)

    if cached and not force_reload:
        if doc == "summary":
            return {"summary": cached.get("summary"), "detail": None}
        if doc == "detail":
            return {"summary": None, "detail": cached.get("detail")}
        return {"summary": cached.get("summary"), "detail": cached.get("detail")}

    root = get_workspace_root()
    docs_dir = _gh_planner_docs_dir(root)

    def _read(name: str) -> str | None:
        p = docs_dir / name
        return p.read_text(encoding="utf-8") if p.exists() else None

    summary = _read("project_summary.md")
    detail = _read("project_detail.md")

    _PROJECT_DOCS_CACHE[resolved] = {"summary": summary, "detail": detail, "loaded_at": time.time()}

    if doc == "summary":
        return {"summary": summary, "detail": None}
    if doc == "detail":
        return {"summary": None, "detail": detail}
    return {"summary": summary, "detail": detail}


def _do_docs_exist(repo: str | None = None) -> dict:
    root = get_workspace_root()
    docs_dir = _gh_planner_docs_dir(root)
    summary_path = docs_dir / "project_summary.md"
    detail_path = docs_dir / "project_detail.md"

    summary_exists = summary_path.exists()
    detail_exists = detail_path.exists()
    age_hours: float | None = None
    if summary_exists:
        age_hours = (time.time() - summary_path.stat().st_mtime) / 3600

    # Parse sections and populate _PROJECT_DOCS_CACHE so the immediately-following
    # lookup_feature_section() call gets a cache hit (zero extra disk reads).
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
        # Also cache summary text if not already present
        if entry.get("summary") is None and summary_exists:
            entry["summary"] = summary_path.read_text(encoding="utf-8")

    return {
        "summary_exists": summary_exists,
        "detail_exists": detail_exists,
        "summary_age_hours": age_hours,
        "sections": sections,
    }


# ── Section-level helpers ─────────────────────────────────────────────────────


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


def _do_lookup_feature_section(feature: str, repo: str | None = None) -> dict:
    """Return the project_detail.md section whose H2 heading best matches `feature`.

    Matching order: exact → substring → first prefix match.
    Also returns global_rules from project_summary.md and the full list of
    available feature headings so Claude can suggest adding a missing section.
    """
    resolved = _resolve_repo(repo) or "unknown"
    entry = _PROJECT_DOCS_CACHE.setdefault(resolved, {})

    # --- section cache (with mtime-based invalidation) ---
    root = get_workspace_root()
    docs_dir = _gh_planner_docs_dir(root)
    detail_path = docs_dir / "project_detail.md"
    cached_sections: dict[str, str] | None = entry.get("_sections")

    if not detail_path.exists():
        # Serve stale cache if available rather than returning nothing
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
    # 1. exact
    for k in sections:
        if k.lower() == feature_lower:
            matched_key = k
            break
    # 2. substring
    if matched_key is None:
        for k in sections:
            if feature_lower in k.lower() or k.lower() in feature_lower:
                matched_key = k
                break
    # 3. first-word prefix
    if matched_key is None:
        first_word = feature_lower.split()[0] if feature_lower.split() else ""
        for k in sections:
            if first_word and k.lower().startswith(first_word):
                matched_key = k
                break

    # --- global rules (project_summary.md, cached) ---
    global_rules: str | None = entry.get("summary")
    if global_rules is None:
        root = get_workspace_root()
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


# ── File index extraction (Python-side, no raw content sent to Claude) ──────────

_MD_SUFFIXES = {".md", ".rst", ".txt"}
# Key: str(workspace_root) — separate entries per project root to prevent
# cross-workspace contamination when PROJECT_ROOT changes between calls (#94)
_SESSION_HEADER_CACHE: dict[str, dict] = {}


def _extract_file_index(file_path: str, content: str) -> dict:
    """Extract a compact structural summary from a file's content.

    Returns ~30-50 tokens of metadata instead of the raw file text.
    Claude receives this instead of the raw content during repo analysis.
    """
    suffix = Path(file_path).suffix.lower()

    if suffix == ".py":
        try:
            tree = ast.parse(content, filename=file_path)
        except (SyntaxError, ValueError):
            return {"path": file_path, "type": "python", "parse_error": True,
                    "lines": content.count("\n")}
        exports = [
            n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not n.name.startswith("_")
        ]
        imports = [
            node.names[0].name
            for node in ast.walk(tree) if isinstance(node, ast.Import)
        ][:5]
        return {
            "path": file_path,
            "type": "python",
            "exports": exports,
            "imports": imports,
            "module_doc": (ast.get_docstring(tree) or "")[:120],
            "lines": content.count("\n"),
        }

    if suffix in _MD_SUFFIXES:
        headings = [
            ln.lstrip("# ").strip()
            for ln in content.splitlines() if ln.startswith("#")
        ]
        return {
            "path": file_path,
            "type": "markdown",
            "headings": headings[:10],
            "first_200": content[:200],
        }

    return {"path": file_path, "type": "other", "lines": content.count("\n")}


def _file_hash_path(root: Path) -> Path:
    return _gh_planner_docs_dir(root) / "file_hashes.json"


def _load_file_hashes(root: Path) -> dict[str, str]:
    p = _file_hash_path(root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_file_hashes(root: Path, hashes: dict[str, str]) -> None:
    p = _file_hash_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    os.replace(tmp, p)


# ── get_file_tree ─────────────────────────────────────────────────────────────

def _file_tree_cache_path(root: Path) -> Path:
    return _gh_planner_docs_dir(root) / "file_tree.json"


def _should_ignore(name: str) -> bool:
    """Return True if directory/file name matches an ignore pattern."""
    if name in _FILE_TREE_IGNORE:
        return True
    for pat in _FILE_TREE_IGNORE:
        if pat.startswith("*") and name.endswith(pat[1:]):
            return True
    return False


def _build_file_tree(root: Path) -> tuple[dict, list[str]]:
    """Walk root directory, return (nested_tree, flat_index) excluding ignored paths."""
    flat: list[str] = []

    def _walk(directory: Path, rel_prefix: str) -> dict:
        node: dict = {}
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return node
        for entry in entries:
            if _should_ignore(entry.name):
                continue
            rel = f"{rel_prefix}{entry.name}"
            if entry.is_dir():
                children = _walk(entry, rel + "/")
                node[entry.name + "/"] = children
            else:
                node[entry.name] = {"size": entry.stat().st_size, "ext": entry.suffix.lower()}
                flat.append(rel)
        return node

    tree = _walk(root, "")
    return tree, flat


def _do_get_file_tree(refresh: bool = False) -> dict:
    """Return a cached file-tree index of the workspace root.

    Cached in memory and on disk under hub_agents/extensions/gh_planner/file_tree.json.
    TTL: 1 hour. Pass refresh=True to force re-fetch.
    """
    from datetime import datetime, timezone

    root = get_workspace_root()
    cache_path = _file_tree_cache_path(root)

    # In-memory cache check
    if not refresh and _FILE_TREE_CACHE:
        fetched_at_str = _FILE_TREE_CACHE.get("fetched_at", "")
        try:
            fetched_at = datetime.fromisoformat(fetched_at_str)
            age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
            if age < _FILE_TREE_TTL:
                return dict(_FILE_TREE_CACHE)
        except (ValueError, TypeError):
            pass

    # Disk cache check
    if not refresh and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
            if age < _FILE_TREE_TTL:
                _FILE_TREE_CACHE.clear()
                _FILE_TREE_CACHE.update(cached)
                return dict(cached)
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass

    # Build fresh tree
    tree, flat_index = _build_file_tree(root)
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "fetched_at": now,
        "root": str(root),
        "tree": tree,
        "flat_index": flat_index,
        "total_files": len(flat_index),
        "_display": f"✓ File tree built — {len(flat_index)} files in {root.name}",
    }

    # Write disk cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    os.replace(tmp, cache_path)

    _FILE_TREE_CACHE.clear()
    _FILE_TREE_CACHE.update(result)
    return result


# ── analyze_repo_full ─────────────────────────────────────────────────────────

def _do_analyze_repo_full(repo: str | None = None) -> dict:
    """Fetch the full repo tree, extract structured file index, return in one call.

    Python owns the entire fetch-and-extract loop. Claude receives a compact
    structured index (~30 tokens/file) instead of raw file contents (~150 tokens/file).
    Uses blob SHA comparison to skip unchanged files on re-analysis.
    """
    resolved = _resolve_repo(repo)
    if not resolved:
        return {"error": "repo_required",
                "message": "Pass repo=\'owner/repo\' or configure via setup_workspace.",
                "_hook": None}

    gh, err = _get_github_client()
    if gh is None:
        return {"error": "github_unavailable", "message": err, "_guidance": _G_AUTH}

    root = get_workspace_root()
    stored_hashes = _load_file_hashes(root)

    # Step 1: fetch tree (1 API call, returns SHAs for free)
    try:
        with gh:
            tree = gh.list_repo_tree()
    except Exception as exc:
        return {"error": "github_error", "message": str(exc), "_hook": None}

    raw_tree_len = len(tree)
    tree = tree[:_MAX_ANALYSIS_FILES]
    omitted_files = max(0, raw_tree_len - len(tree))

    # Step 2: partition — skip files whose SHA hasn\'t changed
    new_hashes: dict[str, str] = {}
    to_fetch = []
    skipped_unchanged = 0

    for f in tree:
        path = f["path"]
        # Skip binary files — fetching them produces no usable index data
        if Path(path).suffix.lower() in _BINARY_EXTENSIONS:
            skipped_unchanged += 1
            continue
        # Use SHA from git tree for incremental skip (unchanged files)
        tree_sha = f.get("sha", "")
        if tree_sha and stored_hashes.get(path) == tree_sha:
            skipped_unchanged += 1
            new_hashes[path] = tree_sha
        else:
            to_fetch.append(f)

    # Step 3: fetch only changed/new files, extract index inline
    file_index = []
    skipped_errors = []

    if to_fetch:
        with gh:
            for f in to_fetch:
                path = f["path"]
                try:
                    content = gh.get_file_content(path)
                    entry = _extract_file_index(path, content)
                    file_index.append(entry)
                    # Store SHA if available, else content hash
                    sha = f.get("sha") or hashlib.sha256(content.encode()).hexdigest()[:32]
                    new_hashes[path] = sha
                except Exception as exc:
                    reason = getattr(exc, "error_code", "unknown")
                    skipped_errors.append({"path": path, "reason": reason})

    # Persist updated hashes
    _save_file_hashes(root, new_hashes)

    # Invalidate file-tree cache — the tree may have new files after analysis
    _FILE_TREE_CACHE.clear()

    # Also update analysis cache so get_analysis_status works
    _ANALYSIS_CACHE[resolved] = {
        "pending_md": [], "pending_code": [],
        "analyzed": [{"path": e["path"], "is_markdown": e["type"] == "markdown"}
                     for e in file_index],
        "skipped": skipped_errors,
        "repo": resolved,
        "started_at": time.time(),
        "last_fetched": time.time(),
    }

    cap_warning = (
        f"\n  ⚠ {omitted_files} files omitted (repo exceeds {_MAX_ANALYSIS_FILES}-file cap)"
        if omitted_files > 0 else ""
    )
    return {
        "repo": resolved,
        "file_index": file_index,
        "total_files": len(tree),
        "fetched": len(file_index),
        "skipped_unchanged": skipped_unchanged,
        "skipped_errors": len(skipped_errors),
        "omitted_files": omitted_files,
        "_display": (
            f"✓ Repo analyzed — {resolved}\n"
            f"  Files fetched : {len(file_index)} "
            f"({skipped_unchanged} unchanged, {len(skipped_errors)} skipped)"
            f"{cap_warning}"
        ),
    }


# ── get_session_header ─────────────────────────────────────────────────────────

def _do_get_session_header() -> dict:
    """Return a ≤120-token context blob for session start. Cached after first call.

    Tells Claude whether project docs exist, how fresh they are, a one-line
    summary title, and the list of feature-area sections in project_detail.md.
    Claude loads full summary/section only when planning context is needed.
    """
    root = get_workspace_root()
    root_key = str(root)
    # Cache keyed by workspace root to prevent cross-project contamination (#94)
    if root_key in _SESSION_HEADER_CACHE:
        return _SESSION_HEADER_CACHE[root_key]

    docs_dir = _gh_planner_docs_dir(root)
    summary_path = docs_dir / "project_summary.md"
    detail_path = docs_dir / "project_detail.md"

    if not summary_path.exists():
        result: dict = {"docs": False}
        _SESSION_HEADER_CACHE[root_key] = result
        return result

    age_h = (time.time() - summary_path.stat().st_mtime) / 3600
    first_line = summary_path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()

    # Surface section index so Claude knows which feature areas have detail
    # Capped at 10 entries to stay within the ≤120-token budget (#67)
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


# ── list_issues with compact mode ─────────────────────────────────────────────

def _do_list_issues(compact: bool = False) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    issues = list_issue_files(root)
    # Mark issues that have never been submitted to GitHub (#102)
    for issue in issues:
        if not issue.get("issue_number"):
            issue["local_only"] = True
    if compact:
        issues = [{"slug": i["slug"], "title": i["title"], "status": i["status"],
                   **({"local_only": True} if i.get("local_only") else {})}
                  for i in issues]
    result: dict = {"issues": issues}
    # Hint to sync if cache is stale (#113)
    if _issues_cache_stale(root):
        result["_suggest_sync"] = (
            "Issue cache is empty or stale. Call sync_github_issues() to fetch "
            "the latest issues from GitHub at ~30 tokens/issue instead of ~150."
        )
    # Unload suggestion when session caches are heavy (#113)
    if hint := _check_suggest_unload():
        result["_suggest_unload"] = hint
    return result


def _do_list_pending_drafts() -> dict:
    """Return only local-only (unsubmitted) issues. Used to identify drift risk (#102)."""
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    issues = list_issue_files(root)
    pending = [
        {"slug": i["slug"], "title": i["title"], "status": i["status"],
         "created_at": i.get("created_at"), "file": i.get("file")}
        for i in issues
        if not i.get("issue_number")
    ]
    return {"pending_drafts": pending, "count": len(pending)}


# ── GitHub issues sync (#113) ─────────────────────────────────────────────────

_ISSUES_SYNC_TTL = 3600  # seconds — cache considered stale after 1 hour


def _check_suggest_unload() -> str | None:
    """Return an unload suggestion string when session caches are heavy.

    Triggered when analysis, project docs, AND label caches are all populated.
    """
    if _ANALYSIS_CACHE and _PROJECT_DOCS_CACHE and _LABEL_CACHE:
        return (
            "Context is getting heavy. Say 'unload github issue manager' to free memory "
            "and keep things fast, or continue working."
        )
    return None


def _do_sync_github_issues(state: str = "open", refresh: bool = False) -> dict:
    """Fetch issues from GitHub API and write to hub_agents/issues/ as local .md files (#113).

    Uses Python to fetch all issues (paginated), skipping unchanged ones.
    Records issues_synced_at in github_local_config.json.

    Returns {synced, skipped, total, _display}.
    """
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    valid_states = {"open", "closed", "all"}
    if state not in valid_states:
        return {"error": "invalid_state", "message": f"state must be one of {sorted(valid_states)}"}

    gh, error_message = get_github_client()
    if gh is None:
        return {"error": "github_unavailable", "message": error_message, "_guidance": _G_AUTH}

    with gh:
        try:
            raw_issues = gh.list_issues_all(state=state)
        except Exception as exc:
            return {"error": "github_error", "message": str(exc)}

    issues_dir = root / "hub_agents" / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)

    # Build lookup of existing local files by issue_number for skip check
    existing_by_number: dict[int, dict] = {}
    for existing in list_issue_files(root):
        num = existing.get("issue_number")
        if num:
            existing_by_number[num] = existing

    synced = 0
    skipped = 0

    for raw in raw_issues:
        # Skip pull requests (GitHub returns PRs in issues endpoint)
        if raw.get("pull_request"):
            continue

        number = raw.get("number")
        title = raw.get("title", "")
        body = raw.get("body") or ""
        issue_state = raw.get("state", "open")
        labels = [l["name"] for l in raw.get("labels", [])]
        assignees = [a["login"] for a in raw.get("assignees", [])]
        created_at_str = raw.get("created_at", "")
        updated_at_str = raw.get("updated_at", "")
        github_url = raw.get("html_url", "")

        # Build slug: {number}-{slugified-title}
        base_slug = f"{number}-{slugify(title)}" if number else slugify(title)
        if not base_slug:
            base_slug = str(number or "unknown")

        # Skip if already exists and not refreshing and not changed
        if not refresh and number in existing_by_number:
            existing = existing_by_number[number]
            # Read existing file to check updated_at
            existing_path = issues_dir / f"{existing['slug']}.md"
            if existing_path.exists():
                content = existing_path.read_text(encoding="utf-8")
                if updated_at_str and updated_at_str in content:
                    skipped += 1
                    continue

        # Map GitHub state to IssueStatus
        issue_status = IssueStatus.OPEN if issue_state == "open" else IssueStatus.CLOSED

        # Parse created_at date
        try:
            import datetime as _dt
            created_date = _dt.datetime.fromisoformat(
                created_at_str.replace("Z", "+00:00")
            ).date()
        except (ValueError, AttributeError):
            created_date = date.today()

        # Build body with metadata footer
        body_with_meta = body
        if updated_at_str:
            body_with_meta = f"{body}\n\n<!-- synced_at: {updated_at_str} -->"

        # Use fixed slug: number-title to avoid collisions with re-syncs
        slug = base_slug
        # If a different slug exists for this number, reuse it
        if number in existing_by_number:
            slug = existing_by_number[number]["slug"]

        write_issue_file(
            root=root,
            slug=slug,
            title=title,
            body=body_with_meta,
            assignees=assignees,
            labels=labels,
            created_at=created_date,
            status=issue_status,
            issue_number=number,
            github_url=github_url,
        )
        synced += 1

    # Record sync timestamp in github_local_config.json
    _do_save_github_local_config({"issues_synced_at": time.time(), "issues_state": state})

    total = len(raw_issues)
    env = read_env(root)
    repo = env.get("GITHUB_REPO", "unknown")
    return {
        "synced": synced,
        "skipped": skipped,
        "total": total,
        "state": state,
        "_display": (
            f"✓ Synced {synced} issue(s) from {repo} ({state})\n"
            f"  Skipped {skipped} unchanged | Total fetched: {total}\n"
            f"  Stored in hub_agents/issues/"
        ),
    }


def _issues_cache_stale(root: Path) -> bool:
    """Return True if local issue cache is empty or older than _ISSUES_SYNC_TTL."""
    config_path = _local_config_path(root)
    if not config_path.exists():
        return True
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        synced_at = data.get("issues_synced_at")
        if not synced_at:
            return True
        return (time.time() - float(synced_at)) > _ISSUES_SYNC_TTL
    except (json.JSONDecodeError, OSError, ValueError):
        return True


# ── Existing docs detection (#84) ─────────────────────────────────────────────

_DOC_LIKE_PATTERNS = frozenset([
    "readme", "design", "architecture", "spec", "contributing",
    "changelog", "changes", "history", "docs/", "documentation/",
])


def detect_existing_docs(file_index: list[dict]) -> list[dict]:
    """From analyze_repo_full file_index, return doc-like .md files.

    Matches top-level README/DESIGN/ARCHITECTURE or files under docs/ directory.
    Returns list of {path, size} dicts for Claude to present to the user.
    """
    results = []
    for f in file_index:
        path: str = f.get("path", "").lower()
        if not path.endswith(".md"):
            continue
        base = path.rsplit("/", 1)[-1].rstrip(".md").lower() if "/" in path else path.rstrip(".md").lower()
        if any(pat in path or base.startswith(pat.rstrip("/")) for pat in _DOC_LIKE_PATTERNS):
            results.append({"path": f["path"], "size": f.get("size", 0)})
    return results


def _do_save_docs_strategy(
    strategy: str,
    referred_docs: list[str] | None = None,
) -> dict:
    """Persist existing-docs strategy to hub_agents/extensions/gh_planner/docs_strategy.json (#84).

    strategy: one of 'refer', 'overwrite', 'merge', 'ignore'
    referred_docs: list of file paths (only meaningful for strategy='refer')
    """
    root = get_workspace_root()
    if err := ensure_initialized(root):
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
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    strategy_path = _gh_planner_docs_dir(root) / "docs_strategy.json"
    if not strategy_path.exists():
        return {"strategy": None, "referred_docs": []}
    try:
        data = json.loads(strategy_path.read_text(encoding="utf-8"))
        return {"strategy": data.get("strategy"), "referred_docs": data.get("referred_docs", [])}
    except (json.JSONDecodeError, OSError):
        return {"strategy": None, "referred_docs": []}


# ── Label analysis (#81) ──────────────────────────────────────────────────────

def _do_analyze_github_labels(refresh: bool = False) -> dict:
    """Fetch labels from GitHub, classify active vs closed, save to github_local_config.json (#81).

    active_labels: labels with open issues or created < 30 days ago.
    closed_labels: labels with no open issues and created > 30 days ago.

    On first call for a new repo with only GitHub defaults, suggests project-specific labels.
    """
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    root_key = str(root)
    if not refresh and root_key in _LABEL_CACHE:
        cached = _LABEL_CACHE[root_key]
        return {**cached, "cached": True}

    gh, error_message = get_github_client()
    if gh is None:
        return {"error": "github_unavailable", "message": error_message, "_guidance": _G_AUTH}

    with gh:
        try:
            raw_labels = gh.list_labels()
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

        # Parse created_at to determine age
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

    # Check if only GitHub default labels exist (new repo path)
    all_names = {lbl.get("name", "") for lbl in raw_labels}
    only_defaults = bool(raw_labels) and all_names.issubset(_GITHUB_DEFAULT_LABEL_NAMES)

    result: dict = {
        "active_labels": active_labels,
        "closed_labels": closed_labels,
        "total": len(raw_labels),
        "only_defaults": only_defaults,
    }

    # Save to disk
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

    # Update in-memory cache
    _LABEL_CACHE[root_key] = {
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
    root = get_workspace_root()
    if err := ensure_initialized(root):
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


# ── Global / local config (#80) ───────────────────────────────────────────────

_GLOBAL_CONFIG_DEFAULTS: dict = {
    "auth": {"method": "none", "username": None},
    "default_repo": None,
    "rate_limit_remaining": None,
    "last_checked": None,
}


def _do_load_github_global_config() -> dict:
    """Load hub_agents/github_global_config.json — creates with defaults if absent (#80).

    Stores auth method, username, default_repo, rate_limit_remaining.
    Does NOT store tokens. Never cleared by unload_plugin.
    """
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    path = _global_config_path(root)
    if not path.exists():
        # Populate auth from current token resolution
        token, source = resolve_token()
        defaults = {**_GLOBAL_CONFIG_DEFAULTS}
        if token:
            defaults["auth"] = {"method": source.value, "username": None}
        env = read_env(root)
        if repo := env.get("GITHUB_REPO"):
            defaults["default_repo"] = repo
        defaults["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # Write defaults
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
        import os as _os6; _os6.replace(tmp, path)
        return {**defaults, "created": True}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {**_GLOBAL_CONFIG_DEFAULTS}


def _do_save_github_local_config(data: dict) -> dict:
    """Merge data into hub_agents/extensions/gh_planner/github_local_config.json (#80).

    Performs a shallow merge (top-level keys from data overwrite existing).
    Atomic write via tmp file.
    """
    root = get_workspace_root()
    if err := ensure_initialized(root):
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
    """Return GitHub config for scope: 'global', 'local', or 'both' (#80).

    global: auth method, default_repo, rate_limit metadata.
    local:  project-specific labels, templates, etc.
    both:   merged view with both sections.
    """
    root = get_workspace_root()
    if err := ensure_initialized(root):
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


# ── Plugin unload ─────────────────────────────────────────────────────────────

# All volatile cache files owned by gh_planner (project docs and issues are NOT included)
_GH_PLANNER_VOLATILE_FILES = [
    "analyzer_snapshot.json",
    "file_hashes.json",
    "file_tree.json",
    "github_local_config.json",
]


def _do_list_plugin_state(plugin: str) -> dict:
    """Inventory all gh_planner-managed resources: in-memory caches + disk files."""
    if plugin != "gh_planner":
        return {"error": "unknown_plugin", "message": f"Unknown plugin {plugin!r}. Available: gh_planner"}

    root = get_workspace_root()
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

    # Rough memory estimate: sum string lengths of all cached values / 1024
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
    """Clear all gh_planner in-memory caches and volatile disk files.

    Does NOT remove project docs (project_summary.md, project_detail.md) or issues.
    """
    if plugin != "gh_planner":
        return {"error": "unknown_plugin", "message": f"Unknown plugin {plugin!r}. Available: gh_planner"}

    root = get_workspace_root()
    docs_dir = _gh_planner_docs_dir(root)
    cleared: list[str] = []
    errors: list[str] = []

    # Clear in-memory caches
    for cache, name in [
        (_ANALYSIS_CACHE, "_ANALYSIS_CACHE"),
        (_PROJECT_DOCS_CACHE, "_PROJECT_DOCS_CACHE"),
        (_FILE_TREE_CACHE, "_FILE_TREE_CACHE"),
        (_SESSION_HEADER_CACHE, "_SESSION_HEADER_CACHE"),
        (_LABEL_CACHE, "_LABEL_CACHE"),
    ]:
        if cache:
            cache.clear()
            cleared.append(name)

    # Remove volatile disk files
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
        "_display": "Unloading successful!" if success else f"Unload completed with {len(errors)} error(s): {errors}",
    }


_UNLOAD_POLICY_PATH = _PLUGIN_DIR / "unload_policy.json"

# Map policy key → (in-memory cache dict | None, disk filename | None)
# disk filenames are relative to _gh_planner_docs_dir(root)
_CACHE_KEY_MAP: dict[str, tuple[dict | None, str | None]] = {
    "analysis_cache":       (_ANALYSIS_CACHE,       None),
    "project_docs_cache":   (_PROJECT_DOCS_CACHE,   None),
    "file_tree_cache":      (_FILE_TREE_CACHE,       None),
    "session_header_cache": (_SESSION_HEADER_CACHE,  None),
    "label_cache":          (_LABEL_CACHE,           None),
    "repo_cache":           (_REPO_CACHE,            None),
    "analyzer_snapshot":    (None, "analyzer_snapshot.json"),
    "file_hashes":          (None, "file_hashes.json"),
    "file_tree":            (None, "file_tree.json"),
    "github_local_config":  (None, "github_local_config.json"),
    "docs_strategy":        (None, "docs_strategy.json"),
}


def _load_unload_policy() -> dict:
    """Load and return the full unload_policy.json contents."""
    try:
        return json.loads(_UNLOAD_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": str(exc), "commands": {}}


def _do_apply_unload_policy(command: str) -> dict:
    """Clear only the caches listed in unload_policy.json for the given command."""
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err

    policy = _load_unload_policy()
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
    keep_summary = ", ".join(to_keep) if to_keep else "none"
    cleared_summary = ", ".join(cleared) if cleared else "nothing"
    display = (
        f"✓ Unload policy applied for '{command}'\n"
        f"  Cleared: {cleared_summary}\n"
        f"  Kept:    {keep_summary}"
    )
    return {
        "success": success,
        "command": command,
        "cleared": cleared,
        "kept": to_keep,
        "errors": errors,
        "_display": display,
    }


# ── Plugin registration ───────────────────────────────────────────────────────

def register(mcp) -> None:
    """Register all GitHub-specific MCP tools and resources on the given FastMCP instance."""

    # ── Resources (workflow guides) ───────────────────────────────────────────

    @mcp.resource("terminal-hub://workflow/init")
    def workflow_init() -> str:
        """Step-by-step guide for initialising a new project workspace."""
        return _load_agent("github-planner/setup.md")

    @mcp.resource("terminal-hub://workflow/issue")
    def workflow_issue() -> str:
        """Guide for creating, listing, and reloading issue context."""
        return _load_agent("github-planner/create-issue.md")

    @mcp.resource("terminal-hub://workflow/context")
    def workflow_context() -> str:
        """Guide for loading and saving project description and architecture."""
        return _load_agent("github-planner.md")

    @mcp.resource("terminal-hub://workflow/auth")
    def workflow_auth() -> str:
        """Auth recovery guide — check_auth → gh auth login → verify_auth."""
        return _load_agent("github-planner/auth.md")

    # ── Auth tools ────────────────────────────────────────────────────────────

    @mcp.tool()
    def check_auth() -> dict:
        """Check GitHub authentication status.
        If not authenticated, presents login options to show the user.
        Call this whenever a GitHub tool returns an auth error."""
        return _do_check_auth()

    @mcp.tool()
    def verify_auth() -> dict:
        """Verify GitHub CLI authentication after the user runs gh auth login.
        Call this after the user reports they have completed gh auth login."""
        return _do_verify_auth()

    # ── Issue tools ───────────────────────────────────────────────────────────

    @mcp.tool()
    def draft_issue(
        title: str,
        body: str,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
        note: str | None = None,
    ) -> dict:
        """Save an issue draft locally as status=pending.

        Returns {slug, title, preview_body, status} so Claude can show the user
        a preview and ask for approval before calling submit_issue.
        Local-only users can stop here — the draft is cached in hub_agents/issues/.

        note: optional meta-note about user intent or experience level — stored in
        front matter for agent reference. Example: "user wants X, may need guidance
        on Y — suggest step-by-step approach"
        """
        return _do_draft_issue(title, body, labels, assignees, note=note)

    @mcp.tool()
    def generate_issue_workflows(slug: str) -> dict:
        """Append agent + program workflow scaffolding to an existing issue file.

        Call after draft_issue (or for any existing issue) to add structured workflow
        sections: orient → plan → implement → verify, plus a change-type-aware test plan.
        Idempotent — skips if workflow sections already exist (#88)."""
        return _do_generate_issue_workflows(slug)

    @mcp.tool()
    def submit_issue(slug: str) -> dict:
        """Submit a pending local issue draft to GitHub.

        Reads the local hub_agents/issues/<slug>.md file, bootstraps any missing
        labels, creates the GitHub issue, then updates the local file to status=open.

        Call this only after the user has approved the draft shown by draft_issue.
        On any failure Claude handles the error directly — no automatic retry.
        """
        return _do_submit_issue(slug)

    @mcp.tool()
    def list_issues(compact: bool = False) -> dict:
        """Return tracked issues from local hub_agents/issues/ files.
        compact=True: returns [{slug, title, status}] only (~3× fewer tokens).
        compact=False (default): returns full issue metadata.
        Issues never submitted to GitHub are marked with local_only: true (#102).
        If cache is stale, _suggest_sync hints to call sync_github_issues() first (#113)."""
        return _do_list_issues(compact)

    @mcp.tool()
    def sync_github_issues(state: str = "open", refresh: bool = False) -> dict:
        """Fetch GitHub issues and cache them locally as .md files (#113).

        Python fetches all issues (paginated) and writes to hub_agents/issues/.
        ~30 tokens/issue vs ~150 tokens if Claude were to relay raw API responses.

        state: 'open' (default), 'closed', or 'all'
        refresh: True to re-fetch all issues even if unchanged (default: skip unchanged)

        Returns {synced, skipped, total, _display}.
        After syncing, call list_issues() to read the cached results.
        """
        return _do_sync_github_issues(state, refresh)

    @mcp.tool()
    def list_pending_drafts() -> dict:
        """Return only issues that exist locally but have never been submitted to GitHub.
        Use to identify status drift risk — local issues may diverge from GitHub state (#102)."""
        return _do_list_pending_drafts()

    @mcp.tool()
    def get_issue_context(slug: str) -> dict:
        """Read a specific issue file by slug to reload context cheaply."""
        return _do_get_issue_context(slug)

    # ── Project context tools ─────────────────────────────────────────────────

    @mcp.tool()
    def update_project_detail_section(feature_name: str, content: str) -> dict:
        """Merge a single H2 section into project_detail.md without rewriting the full file.

        If '## {feature_name}' already exists, replaces that section only.
        Otherwise appends a new section. Use instead of save_project_docs when
        adding/updating a single feature area to avoid accidental truncation (#65).

        Decision rule for when to call:
        - Issue labels include 'enhancement' or 'feature' → call this
        - Issue labels include 'architecture' → call this for Design Principles section
        - Labels are only 'bug', 'chore', 'refactor', 'docs' → do NOT call (no doc update)
        - No labels → ask user first"""
        return _do_update_project_detail_section(feature_name, content)

    @mcp.tool()
    def update_project_description(content: str) -> dict:
        """Overwrite hub_agents/project_description.md.
        Call get_project_context first to preserve existing content."""
        return _do_update_project_description(content)

    @mcp.tool()
    def update_architecture(content: str) -> dict:
        """Overwrite hub_agents/architecture_design.md.
        Call get_project_context first to preserve existing content."""
        return _do_update_architecture(content)

    @mcp.tool()
    def set_preference(key: str, value: bool) -> dict:
        """Persist a user preference in hub_agents/config.yaml.
        Supported keys: confirm_arch_changes (bool), github_repo_connected (bool).
        confirm_arch_changes=True → always ask before auto-updating project docs.
        confirm_arch_changes=False → auto-update docs silently.
        github_repo_connected tracks whether a GitHub repo has been linked."""
        return _do_set_preference(key, value)

    @mcp.tool()
    def create_github_repo(name: str, description: str, private: bool = True) -> dict:
        """Create a new GitHub repo under the authenticated user and link it to this workspace.

        Call this when the user wants terminal-hub to set up their GitHub repo automatically.
        Ask for public/private preference before calling.
        name: repo name (no owner prefix — GitHub adds it automatically)
        description: short repo description (used as the GitHub repo description)
        private: True for private, False for public"""
        return _do_create_github_repo(name, description, private)

    @mcp.tool()
    def get_project_context(doc_key: str) -> dict:
        """Read project_description.md and/or architecture_design.md from hub_agents/.
        doc_key: 'project_description', 'architecture', or 'all'."""
        return _do_get_project_context(doc_key)

    @mcp.tool()
    def save_docs_strategy(strategy: str, referred_docs: list[str] | None = None) -> dict:
        """Persist how to handle existing .md docs found during repo analysis (#84).

        strategy: 'refer' | 'overwrite' | 'merge' | 'ignore'
        referred_docs: paths of docs to use as context (only for strategy='refer').
        Saved to hub_agents/extensions/gh_planner/docs_strategy.json."""
        return _do_save_docs_strategy(strategy, referred_docs)

    @mcp.tool()
    def load_docs_strategy() -> dict:
        """Load the saved existing-docs strategy for this project (#84).
        Returns {strategy, referred_docs} or {strategy: null} if not set."""
        return _do_load_docs_strategy()

    # ── Analyzer tool ─────────────────────────────────────────────────────────

    @mcp.tool()
    def run_analyzer() -> dict:
        """Analyze the GitHub repo and write a snapshot to hub_agents/analyzer_snapshot.json."""
        return _do_run_analyzer()

    # ── Repo analysis tools ────────────────────────────────────────────────────

    @mcp.tool()
    def start_repo_analysis(repo: str | None = None) -> dict:
        """Fetch the full file tree for a GitHub repo and queue files for analysis.

        Partitions files: markdown/docs first, code second (smallest first).
        Caps at 200 files. Stores state in the MCP server runtime cache.
        repo: 'owner/repo' — omit to use the configured GITHUB_REPO.
        """
        return _do_start_repo_analysis(repo)

    @mcp.tool()
    def fetch_analysis_batch(repo: str | None = None, batch_size: int = 5) -> dict:
        """Fetch the next batch of files from the analysis queue and return their contents.

        Call start_repo_analysis first. Markdown files are returned before code files.
        Repeat until done==True. batch_size: 1–20 (default 5).
        Returns {files: [{path, content, is_markdown}], analyzed_count, remaining_count, done}.
        """
        return _do_fetch_analysis_batch(repo, batch_size)

    @mcp.tool()
    def get_analysis_status(repo: str | None = None) -> dict:
        """Return the current analysis progress from the runtime cache (no I/O).

        Returns {analyzed_count, remaining_count, analyzed_paths, remaining_paths, done}.
        """
        return _do_get_analysis_status(repo)

    # ── Project docs tools ────────────────────────────────────────────────────

    @mcp.tool()
    def save_project_docs(summary_md: str, detail_md: str, repo: str | None = None) -> dict:
        """Write project_summary.md and project_detail.md to hub_agents/extensions/gh_planner/.

        summary_md: ≤400-token project overview, tech stack, and pitfalls.
        detail_md: per-file descriptions, unique behaviours, cross-references.
        Both files are written atomically.
        """
        return _do_save_project_docs(summary_md, detail_md, repo)

    @mcp.tool()
    def load_project_docs(doc: str = "summary", repo: str | None = None, force_reload: bool = False) -> dict:
        """Read project docs from cache (fast) or disk.

        doc: 'summary', 'detail', or 'all'.
        force_reload: bypass cache and re-read from disk.
        Returns {summary: str|None, detail: str|None}.
        """
        return _do_load_project_docs(doc, repo, force_reload)

    @mcp.tool()
    def docs_exist(repo: str | None = None) -> dict:
        """Check whether project_summary.md and project_detail.md exist on disk.

        Returns {summary_exists, detail_exists, summary_age_hours, sections}.
        sections: list of H2 headings from project_detail.md — use to decide
        whether a relevant feature section exists before calling lookup_feature_section.
        """
        return _do_docs_exist(repo)

    @mcp.tool()
    def lookup_feature_section(feature: str, repo: str | None = None) -> dict:
        """Return the project_detail.md section whose heading best matches `feature`.

        Matching order: exact → substring → prefix. Uses section-level cache so
        only the matching section (not the full detail doc) is returned to Claude.

        Returns:
          matched=True:  {feature, section, global_rules, available_features}
          matched=False: {available_features, global_rules, reason?}

        Call this BEFORE drafting any issue body when project_detail.md exists.
        If matched=False, show available_features and ask the user whether to add
        rules for this feature before proceeding.
        """
        return _do_lookup_feature_section(feature, repo)

    # ── Efficient single-call repo analysis ────────────────────────────────────

    @mcp.tool()
    def analyze_repo_full(repo: str | None = None) -> dict:
        """Fetch the full repo tree and return a compact structured file index in one call.

        Python fetches files and extracts structural metadata (exports, headings, imports).
        Claude receives ~30 tokens/file instead of ~150 tokens/file of raw content.
        Uses blob SHA comparison to skip unchanged files on re-analysis.
        Returns {repo, file_index, total_files, fetched, skipped_unchanged, skipped_errors}.
        """
        return _do_analyze_repo_full(repo)

    @mcp.tool()
    def get_session_header() -> dict:
        """Return a ≤80-token context blob for session start. Cached after first call.

        Returns {docs: bool, age_hours?, title?, stale?}.
        Call at session start to decide whether to load full project docs.
        """
        return _do_get_session_header()

    @mcp.tool()
    def get_file_tree(refresh: bool = False) -> dict:
        """Return an organized file-tree index of the workspace root.

        Cached in memory and on disk (TTL 1 hour). Use refresh=True to force
        a re-walk of the filesystem. Excludes .git, __pycache__, venv, etc.

        Returns {tree, flat_index, total_files, fetched_at, root}.
        Use flat_index for quick path lookups; tree for navigating structure.
        """
        return _do_get_file_tree(refresh)

    @mcp.tool()
    def list_plugin_state(plugin: str = "gh_planner") -> dict:
        """Inventory all resources loaded by a plugin: in-memory caches and disk files.

        Use before unload_plugin to see what will be cleared.
        Returns {caches: [...], disk_files: [...], total_caches, total_disk_files}.
        """
        return _do_list_plugin_state(plugin)

    @mcp.tool()
    def unload_plugin(plugin: str = "gh_planner") -> dict:
        """Clear all in-memory caches and volatile disk files for a plugin.

        Does NOT remove project docs (project_summary.md, project_detail.md) or issues.
        On success returns {success: true, cleared: [...], _display: "Unloading successful!"}.
        On error returns {success: false, errors: [...]} — analyze errors and retry.
        """
        return _do_unload_plugin(plugin)

    @mcp.tool()
    def apply_unload_policy(command: str) -> dict:
        """Apply the unload policy for a command from unload_policy.json.

        Selectively clears only the caches listed in the command's unload[] array,
        preserving everything in keep[]. Persistent state (issues, project docs,
        config.yaml, .env) is never touched.

        Returns {cleared: [...], kept: [...], _display: "..."}.

        Common command values: 'github-planner', 'github-planner/analyze',
        'github-planner/create-issue', 'github-planner/unload', 'create-github-repo'.
        """
        return _do_apply_unload_policy(command)

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
