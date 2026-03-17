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
    read_doc_file,
    read_issue_file,
    read_issue_frontmatter,
    resolve_slug,
    update_issue_status,
    validate_slug,
    write_doc_file,
    write_issue_file,
)
from extensions.github_planner.client import GitHubClient, GitHubError, load_default_labels
from extensions.github_planner.auth import get_auth_options, resolve_token, verify_gh_cli_auth
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
    repo = detect_repo(root)
    if not repo:
        return None, (
            "No GitHub repo configured for this project. "
            "Call setup_workspace with github_repo='owner/repo' to set one."
        )

    return GitHubClient(token=token, repo=repo), ""


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


def _do_draft_issue(
    title: str,
    body: str,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
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

    base_slug = slugify(title)
    if not base_slug:
        return {"error": "draft_failed", "message": "Title produced an empty slug — use at least one alphanumeric character.", "_hook": None}

    slug = resolve_slug(root, base_slug)

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
    """Return explicit repo or fall back to env / single cached entry."""
    if repo:
        return repo
    if len(_ANALYSIS_CACHE) == 1:
        return next(iter(_ANALYSIS_CACHE))
    root = get_workspace_root()
    env = read_env(root)
    return env.get("GITHUB_REPO")


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
    # #61 — invalidate session header so next call reflects fresh docs
    _SESSION_HEADER_CACHE.clear()

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
_SESSION_HEADER_CACHE: dict = {}


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
    if _SESSION_HEADER_CACHE:
        return _SESSION_HEADER_CACHE

    root = get_workspace_root()
    docs_dir = _gh_planner_docs_dir(root)
    summary_path = docs_dir / "project_summary.md"
    detail_path = docs_dir / "project_detail.md"

    if not summary_path.exists():
        _SESSION_HEADER_CACHE.update({"docs": False})
        return _SESSION_HEADER_CACHE

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

    result: dict = {
        "docs": True,
        "age_hours": round(age_h, 1),
        "title": first_line,
        "stale": age_h > 168,
        "sections": sections,
    }
    if total_sections > _MAX_SECTIONS_IN_HEADER:
        result["sections_truncated"] = True
        result["total_sections"] = total_sections
    _SESSION_HEADER_CACHE.update(result)
    return _SESSION_HEADER_CACHE


# ── list_issues with compact mode ─────────────────────────────────────────────

def _do_list_issues(compact: bool = False) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    issues = list_issue_files(root)
    if compact:
        issues = [{"slug": i["slug"], "title": i["title"], "status": i["status"]}
                  for i in issues]
    return {"issues": issues}


# ── Plugin unload ─────────────────────────────────────────────────────────────

# All volatile cache files owned by gh_planner (project docs and issues are NOT included)
_GH_PLANNER_VOLATILE_FILES = [
    "analyzer_snapshot.json",
    "file_hashes.json",
    "file_tree.json",
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
        caches.append({"name": "_SESSION_HEADER_CACHE"})

    disk_files = []
    for fname in _GH_PLANNER_VOLATILE_FILES:
        p = docs_dir / fname
        if p.exists():
            disk_files.append({"path": str(p.relative_to(root)), "size_bytes": p.stat().st_size})

    return {
        "plugin": plugin,
        "caches": caches,
        "disk_files": disk_files,
        "total_caches": len(caches),
        "total_disk_files": len(disk_files),
        "_display": (
            f"gh_planner state: {len(caches)} in-memory cache(s), {len(disk_files)} disk file(s)"
        ),
    }


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
        return _load_agent("create.md")

    @mcp.resource("terminal-hub://workflow/context")
    def workflow_context() -> str:
        """Guide for loading and saving project description and architecture."""
        return _load_agent("context.md")

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
    ) -> dict:
        """Save an issue draft locally as status=pending.

        Returns {slug, title, preview_body, status} so Claude can show the user
        a preview and ask for approval before calling submit_issue.
        Local-only users can stop here — the draft is cached in hub_agents/issues/.
        """
        return _do_draft_issue(title, body, labels, assignees)

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
        compact=False (default): returns full issue metadata."""
        return _do_list_issues(compact)

    @mcp.tool()
    def get_issue_context(slug: str) -> dict:
        """Read a specific issue file by slug to reload context cheaply."""
        return _do_get_issue_context(slug)

    # ── Project context tools ─────────────────────────────────────────────────

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
    def get_project_context(doc_key: str) -> dict:
        """Read project_description.md and/or architecture_design.md from hub_agents/.
        doc_key: 'project_description', 'architecture', or 'all'."""
        return _do_get_project_context(doc_key)

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
