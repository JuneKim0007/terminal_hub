"""gh_implementation extension — end-to-end issue implementation flow.

Tools: get_implementation_session, set_implementation_session_flag,
       fetch_github_issues, update_issue_frontmatter,
       close_github_issue, delete_local_issue,
       run_tests_filtered
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from extensions.gh_management.github_planner import get_github_client, get_workspace_root, ensure_initialized
from extensions.gh_management.github_planner.storage import (
    _issues_dir, _atomic_write, validate_slug,
    read_issue_frontmatter, list_issue_files, IssueStatus, write_issue_file,
)
from terminal_hub.env_store import read_env
from terminal_hub.constants import COVERAGE_THRESHOLD
from terminal_hub.utils.test_filter import filter_test_results

# ── In-memory session state ───────────────────────────────────────────────────
# Keyed by workspace root str so multi-workspace scenarios don't collide.
_SESSION_FLAGS: dict[str, dict[str, Any]] = {}

_DEFAULT_FLAGS: dict[str, Any] = {
    "close_automatically_on_gh": True,
    "delete_local_issue_on_gh": True,
    "confirmed_auto_close_this_session": False,  # internal — True after "don't ask again"
    "active_issue_slug": None,
}

_ALLOWED_SESSION_FLAGS = {"close_automatically_on_gh", "delete_local_issue_on_gh", "auto_switch_modes",
                          "lookup_design_refs", "run_verify", "run_make_test", "sync_docs_on_close"}


def _load_persistent_flags(root: Path) -> None:
    """Load flags from hub_agents/config.yaml into _SESSION_FLAGS on first use."""
    key = str(root)
    if key in _SESSION_FLAGS:
        return  # already loaded this session
    flags = dict(_DEFAULT_FLAGS)
    # Load from config.yaml if it exists
    config_path = root / "hub_agents" / "config.yaml"
    if config_path.exists():
        try:
            import yaml as _yaml
            data = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            gh_impl = data.get("gh_implementation", {})
            for k in _ALLOWED_SESSION_FLAGS:
                if k in gh_impl:
                    flags[k] = gh_impl[k]
        except Exception:
            pass  # config load failure is non-fatal
    _SESSION_FLAGS[key] = flags


def _get_flags(root: Path) -> dict[str, Any]:
    key = str(root)
    _load_persistent_flags(root)
    if key not in _SESSION_FLAGS:
        _SESSION_FLAGS[key] = dict(_DEFAULT_FLAGS)
    return _SESSION_FLAGS[key]


def _do_get_implementation_session() -> dict:
    root = get_workspace_root()
    flags = _get_flags(root)
    display = (
        "Implementation session flags\n"
        "────────────────────────────────────────\n"
        f"  close_automatically_on_gh   {'true' if flags['close_automatically_on_gh'] else 'false'}"
        "    Push, close branch, and close GitHub issue automatically after accepting changes\n"
        f"  delete_local_issue_on_gh    {'true' if flags['delete_local_issue_on_gh'] else 'false'}"
        "    Delete hub_agents/issues/<slug>.md after GitHub issue is closed\n"
        f"  active_issue_slug           {flags.get('active_issue_slug') or 'none'}"
        "    Currently hooked issue — set automatically by load_active_issue\n"
        "────────────────────────────────────────\n"
        "Say \"change X to false\" or use /th:gh-implementation/session-knowledge to update."
    )
    return {
        "close_automatically_on_gh": flags["close_automatically_on_gh"],
        "delete_local_issue_on_gh": flags["delete_local_issue_on_gh"],
        "_display": display,
    }


def _do_load_active_issue(slug: str) -> dict:
    try:
        validate_slug(slug)
    except ValueError as exc:
        return {"error": "invalid_slug", "message": str(exc)}
    root = get_workspace_root()
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return {"error": "issue_not_found", "message": f"No issue file for slug {slug!r}"}
    content = path.read_text(encoding="utf-8")
    fm = read_issue_frontmatter(root, slug) or {}
    _get_flags(root)["active_issue_slug"] = slug
    return {
        "slug": slug,
        "content": content,
        "title": fm.get("title", ""),
        "labels": fm.get("labels", []),
        "agent_workflow": fm.get("agent_workflow"),
        "_display": f"✅ **Hooked:** issue #{slug} — {fm.get('title', '')} loaded into context",
    }


def _do_unload_active_issue(slug: str | None = None, delete_file: bool | None = None) -> dict:
    root = get_workspace_root()
    flags = _get_flags(root)
    target_slug = slug or flags.get("active_issue_slug")
    if not target_slug:
        return {"unloaded": False, "message": "No active issue in session"}
    flags.pop("active_issue_slug", None)
    should_delete = delete_file if delete_file is not None else flags.get("delete_local_issue_on_gh", True)
    deleted = False
    if should_delete:
        path = _issues_dir(root) / f"{target_slug}.md"
        if path.exists():
            path.unlink()
            deleted = True
    return {
        "unloaded": True,
        "slug": target_slug,
        "file_deleted": deleted,
        "_display": f"✅ **Unhooked:** issue #{target_slug} — context cleared{', file deleted' if deleted else ''}",
    }


def _do_set_implementation_session_flag(key: str, value: bool, persist: bool = False) -> dict:
    if key not in _ALLOWED_SESSION_FLAGS:
        return {"error": "unknown_flag", "message": f"Unknown flag {key!r}. Allowed: {sorted(_ALLOWED_SESSION_FLAGS)}"}
    root = get_workspace_root()
    flags = _get_flags(root)
    flags[key] = value
    result = {"key": key, "value": value, "persisted": False, "_display": f"✅ **Flag set:** `{key}` = {str(value).lower()}"}
    if persist:
        try:
            from terminal_hub.config import write_preference
            write_preference(root, f"gh_implementation.{key}", value)
            result["persisted"] = True
        except Exception as exc:
            result["persist_warning"] = str(exc)
    return result


def _do_fetch_github_issues(state: str = "open", limit: int = 30) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    gh, err = get_github_client()
    if gh is None:
        return err
    issues_dir = _issues_dir(root)
    issues_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    try:
        with gh:
            raw_issues = gh.list_issues(state=state, limit=limit)
    except Exception as exc:
        return {"error": "fetch_failed", "message": str(exc)}

    for issue in raw_issues:
        number = issue.get("number")
        slug = str(number)
        path = issues_dir / f"{slug}.md"
        if path.exists():
            continue  # already synced
        labels = [l["name"] for l in issue.get("labels", [])]
        assignees = [a["login"] for a in issue.get("assignees", [])]
        write_issue_file(
            root=root,
            slug=slug,
            title=issue.get("title", ""),
            body=issue.get("body") or "",
            assignees=assignees,
            labels=labels,
            created_at=date.today(),
            status=IssueStatus.OPEN,
            issue_number=number,
            github_url=issue.get("html_url"),
        )
        created.append(slug)

    n = len(created)
    return {
        "fetched": n,
        "slugs": created,
        "_display": f"✅ **Fetched** {n} issue(s) from GitHub",
    }


def _do_update_issue_frontmatter(slug: str, fields: dict[str, Any]) -> dict:
    """Atomically update specific front matter fields on an existing issue file."""
    try:
        validate_slug(slug)
    except ValueError as exc:
        return {"error": "invalid_slug", "message": str(exc)}
    root = get_workspace_root()
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return {"error": "issue_not_found", "message": f"No issue file for slug {slug!r}"}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {"error": "no_frontmatter", "message": "Issue file has no YAML front matter"}
    parts = text.split("---", 2)
    fm: dict[str, Any] = yaml.safe_load(parts[1]) or {}
    body = parts[2] if len(parts) > 2 else ""
    fm.update(fields)
    updated = f"---\n{yaml.dump(fm, default_flow_style=False)}---{body}"
    _atomic_write(path, updated)
    return {"slug": slug, "updated_fields": list(fields.keys()), "_display": f"✅ **Updated** front matter for #{slug}"}


def _do_close_github_issue(issue_number: int, comment: str | None = None) -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    gh, err = get_github_client()
    if gh is None:
        return err
    try:
        with gh:
            gh.close_issue(issue_number, comment=comment)
        return {
            "issue_number": issue_number,
            "closed": True,
            "_display": f"**✅ Closed** issue #{issue_number} on GitHub",
        }
    except Exception as exc:
        return {"error": "close_failed", "message": str(exc)}


def _do_delete_local_issue(slug: str) -> dict:
    try:
        validate_slug(slug)
    except ValueError as exc:
        return {"error": "invalid_slug", "message": str(exc)}
    root = get_workspace_root()
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return {"error": "not_found", "message": f"No local issue file for {slug!r}"}
    path.unlink()
    return {"deleted": True, "file": f"hub_agents/issues/{slug}.md", "_display": f"🗑 **Deleted** local issue #{slug}"}


def _do_pre_implementation(issue_slug: str, flags_override: dict | None = None) -> dict:
    """Pre-implementation phase: unload previous context, confirm repo, load docs, load issue.

    Replaces the manual 8-call sequence in Steps 1-4 of gh-implementation.md.
    Reads flags from the hybrid session/config system.
    """
    root = get_workspace_root()
    _load_persistent_flags(root)
    flags = _get_flags(root)
    if flags_override:
        flags.update(flags_override)

    # 1. Apply unload policy (clears previous command's caches)
    try:
        from extensions.gh_management.github_planner import _do_apply_unload_policy as _unload
        unload_result = _unload("gh-implementation")
        cache_cleared = unload_result.get("cleared", [])
    except Exception:
        cache_cleared = []

    # 2. Load implementation context (repo confirm + project docs + active issue + design refs)
    try:
        from extensions.gh_management.github_planner.workspace_tools import _do_load_implementation_context
        ctx = _do_load_implementation_context(
            project_root=str(root),
            issue_slug=issue_slug,
            lookup_design_refs=flags.get("lookup_design_refs", True),
        )
    except Exception as exc:
        return {"error": "context_load_failed", "message": str(exc)}

    if "error" in ctx:
        return ctx

    # 3. Load connected docs from docs_config.json (pre_load: true entries)
    connected_docs_loaded = []
    try:
        docs_config_path = root / "hub_agents" / "docs_config.json"
        if docs_config_path.exists():
            import json
            docs_config = json.loads(docs_config_path.read_text(encoding="utf-8"))
            for key, entry in docs_config.items():
                if isinstance(entry, dict) and entry.get("pre_load"):
                    connected_docs_loaded.append(entry.get("path", key))
    except Exception:
        pass

    return {
        "workspace_ready": True,
        "cache_cleared": cache_cleared,
        "repo_confirmed": ctx.get("repo_confirmed"),
        "project_summary": ctx.get("project_summary", ""),
        "active_issue": ctx.get("issue_content", {}),
        "design_sections": ctx.get("design_sections", {}),
        "has_agent_workflow": ctx.get("has_agent_workflow", False),
        "connected_docs_loaded": connected_docs_loaded,
        "flags": {k: flags[k] for k in _ALLOWED_SESSION_FLAGS if k in flags},
        "_display": (
            f"✅ **Context loaded** — issue #{issue_slug}"
            + (f", {len(ctx.get('design_sections', {}))} design sections" if ctx.get("design_sections") else "")
            + (f", {len(connected_docs_loaded)} connected docs" if connected_docs_loaded else "")
        ),
    }


def _do_post_implementation(
    issue_slug: str,
    issue_number: int | None = None,
    affected_files: list[str] | None = None,
    flags_override: dict | None = None,
) -> dict:
    """Post-implementation phase: tests, diff summary, commit/push, close, doc sync, cleanup.

    Runs after Step 6 (implement). Each sub-step is controlled by a flag.
    Does NOT perform git commit/push itself — returns diff and test results for Claude to present.
    Claude calls this once to get test+diff, then calls it again with commit=True after user accepts.
    """
    root = get_workspace_root()
    _load_persistent_flags(root)
    flags = _get_flags(root)
    if flags_override:
        flags.update(flags_override)

    import subprocess
    result: dict = {"issue_slug": issue_slug}

    # 1. Derive affected files
    if affected_files is None:
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, cwd=str(root),
            )
            affected_files = [f for f in proc.stdout.strip().splitlines() if f]
        except Exception:
            affected_files = []
    result["affected_files"] = affected_files

    # 2. Run tests (if flag set)
    test_results: dict = {}
    if flags.get("run_verify", True) and affected_files:
        try:
            tr = _do_run_tests_filtered(affected_files)
            test_results = {
                "passed": tr.get("passed", False),
                "failed": tr.get("failed", 0),
                "coverage": tr.get("coverage", 0.0),
                "meets_threshold": tr.get("meets_threshold", False),
                "filtered_output": tr.get("filtered_output", ""),
            }
        except Exception as exc:
            test_results = {"error": str(exc)}
    result["test_results"] = test_results

    # 3. Git diff summary
    diff_text = ""
    try:
        proc = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, cwd=str(root),
        )
        diff_text = proc.stdout
    except Exception:
        pass

    # Parse diff stats
    insertions = diff_text.count("\n+") - diff_text.count("\n+++")
    deletions = diff_text.count("\n-") - diff_text.count("\n---")
    files_changed = len([l for l in diff_text.splitlines() if l.startswith("diff --git")])
    result["diff"] = {
        "files_changed": files_changed,
        "insertions": max(0, insertions),
        "deletions": max(0, deletions),
        "diff_text": diff_text,
    }

    # 4. Build display
    tests_ok = test_results.get("passed", True) and not test_results.get("error")
    cov = test_results.get("coverage", 0)
    result["_display"] = (
        f"{'✅' if tests_ok else '⚠'} Tests: {test_results.get('failed', 0)} failed, "
        f"coverage {cov:.0f}% | "
        f"Diff: {files_changed} files, +{max(0, insertions)}/-{max(0, deletions)} lines"
    )

    return result


def _do_run_tests_filtered(files: list[str] | None) -> dict:
    import re
    import subprocess

    cmd = [
        "python", "-m", "pytest", "--tb=short", "-q",
        "--cov=terminal_hub", "--cov=extensions", "--cov-report=term-missing",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw = result.stdout + result.stderr

    filtered = filter_test_results(raw, files)

    failed_count = len(re.findall(r"^FAILED ", raw, re.MULTILINE))
    passed_match = re.search(r"(\d+) passed", raw)
    passed_count = int(passed_match.group(1)) if passed_match else 0
    cov_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", raw)
    coverage = float(cov_match.group(1)) if cov_match else 0.0
    raw_summary = "\n".join(raw.strip().splitlines()[-5:])

    passed = failed_count == 0 and result.returncode == 0
    return {
        "passed": passed,
        "failed": failed_count,
        "coverage": coverage,
        "meets_threshold": coverage >= COVERAGE_THRESHOLD,
        "threshold": COVERAGE_THRESHOLD,
        "filtered_output": filtered,
        "raw_summary": raw_summary,
        "_display": (
            f"{'Tests passed' if passed else 'Tests FAILED'} — "
            f"{passed_count} passed, {failed_count} failed — "
            f"coverage {coverage:.0f}% (threshold: {COVERAGE_THRESHOLD}%)"
        ),
    }


def register(mcp: FastMCP) -> None:
    """Register gh_implementation tools on the shared MCP server."""

    @mcp.tool()
    def get_implementation_session() -> dict:
        """Return current session-scoped implementation flags.

        Flags (reset each session unless persisted):
          close_automatically_on_gh: push + close issue on GitHub after user accepts changes
          delete_local_issue_on_gh:  delete local hub_agents/issues/<slug>.md after GH close
        """
        return _do_get_implementation_session()

    @mcp.tool()
    def set_implementation_session_flag(key: str, value: bool, persist: bool = False) -> dict:
        """Update a session-scoped implementation flag.

        key: 'close_automatically_on_gh' | 'delete_local_issue_on_gh' | 'auto_switch_modes'
        value: true | false
        persist: if true, write to hub_agents/config.yaml preferences so it survives sessions
        """
        return _do_set_implementation_session_flag(key, value, persist)

    @mcp.tool()
    def fetch_github_issues(state: str = "open", limit: int = 30) -> dict:
        """Fetch issues from GitHub and write them to hub_agents/issues/.

        Skips issues that already have a local file (by issue number slug).
        state: 'open' | 'closed' | 'all'
        limit: max issues to fetch (default 30)
        Returns {fetched, slugs, _display}.
        """
        return _do_fetch_github_issues(state, limit)

    @mcp.tool()
    def update_issue_frontmatter(slug: str, fields: dict) -> dict:
        """Atomically update specific front matter fields on an existing issue file.

        Only updates the provided keys — leaves body and all other fields unchanged.
        Use this to write agent_workflow, status, or any other front matter field.

        slug: issue slug (e.g. '42' or 'fix-auth-bug')
        fields: dict of front matter keys to update
        """
        return _do_update_issue_frontmatter(slug, fields)

    @mcp.tool()
    def close_github_issue(issue_number: int, comment: str | None = None) -> dict:
        """Close a GitHub issue via the API.

        issue_number: the GitHub issue number (not local slug)
        comment: optional closing comment to post before closing
        """
        return _do_close_github_issue(issue_number, comment)

    @mcp.tool()
    def delete_local_issue(slug: str) -> dict:
        """Delete a local issue file from hub_agents/issues/<slug>.md.

        slug: issue slug (e.g. '42' or 'fix-auth-bug')
        Returns {deleted, file}.
        """
        return _do_delete_local_issue(slug)

    @mcp.tool()
    def load_active_issue(slug: str) -> dict:
        """Hook an issue into the active implementation session.

        Reads hub_agents/issues/<slug>.md, injects full content into the response,
        and sets active_issue_slug in session state.

        Call this as the FIRST action in Step 4 of the implement flow — mandatory.
        The returned content and agent_workflow are the authoritative issue context;
        do not re-read the file separately.

        slug: issue slug (e.g. '42')
        Returns {slug, content, title, labels, agent_workflow, _display}.
        """
        return _do_load_active_issue(slug)

    @mcp.tool()
    def unload_active_issue(slug: str | None = None, delete_file: bool | None = None) -> dict:
        """Unhook the active issue and clean up session state.

        Clears active_issue_slug from session. Deletes the local issue file
        according to the delete_local_issue_on_gh flag unless overridden.

        Call this as the ONLY action in Step 10 of the implement flow — mandatory.

        slug: override the active slug (default: use session-tracked slug)
        delete_file: override the delete_local_issue_on_gh flag (True/False/None=use flag)
        Returns {unloaded, slug, file_deleted, _display}.
        """
        return _do_unload_active_issue(slug, delete_file)

    @mcp.tool()
    def pre_implementation(issue_slug: str, flags_override: dict | None = None) -> dict:
        """Run the pre-implementation phase in one call.

        Replaces the 8-call Steps 1-4 sequence: unload caches, confirm repo,
        load project docs, load active issue, lookup design refs, load connected docs.

        issue_slug: the issue to implement (e.g. '42')
        flags_override: optional dict to override session flags for this call only
        Returns {workspace_ready, repo_confirmed, project_summary, active_issue,
                 design_sections, has_agent_workflow, connected_docs_loaded, flags, _display}
        """
        return _do_pre_implementation(issue_slug, flags_override)

    @mcp.tool()
    def post_implementation(
        issue_slug: str,
        issue_number: int | None = None,
        affected_files: list[str] | None = None,
        flags_override: dict | None = None,
    ) -> dict:
        """Run the post-implementation phase in one call.

        Runs after Step 6 (implement). Derives affected files, runs filtered tests,
        and returns diff summary for Claude to present to the user.

        Does NOT commit/push — Claude reads diff and test results, presents them
        to user, then calls git commit/push via Bash tool after user accepts.

        issue_slug: active issue slug
        issue_number: GitHub issue number (for close step — pass after user accepts)
        affected_files: override auto-derived file list (from git diff --name-only HEAD)
        flags_override: override session flags for this call only
        Returns {affected_files, test_results, diff, _display}
        """
        return _do_post_implementation(issue_slug, issue_number, affected_files, flags_override)

    @mcp.tool()
    def run_tests_filtered(files: list[str] | None = None) -> dict:
        """Run pytest and return results filtered to the given source files.

        Runs the full test suite, then filters stdout through filter_test_results()
        so Claude only receives output relevant to the implementation at hand.

        files: source file paths to filter by (e.g. ['terminal_hub/foo.py']).
               Pass None to return full unfiltered output.
        Returns {passed, failed, coverage, meets_threshold, threshold,
                 filtered_output, raw_summary, _display}.
        """
        return _do_run_tests_filtered(files)
