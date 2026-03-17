"""GitHub Planner plugin for terminal-hub.

Registers all GitHub-specific MCP tools and resources.
Call register(mcp) from create_server() to activate.
"""
from datetime import date
from pathlib import Path

from plugins.github_planner.storage import (
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
from plugins.github_planner.client import GitHubClient, GitHubError, load_default_labels
from plugins.github_planner.auth import get_auth_options, resolve_token, verify_gh_cli_auth
from terminal_hub.env_store import read_env
from terminal_hub.errors import msg
from terminal_hub.slugify import slugify
from terminal_hub.workspace import detect_repo, resolve_workspace_root

_PLUGIN_DIR = Path(__file__).parent
_COMMANDS_DIR = _PLUGIN_DIR / "commands"

# ── Guidance URIs ─────────────────────────────────────────────────────────────
_G_INIT    = "terminal-hub://workflow/init"
_G_ISSUE   = "terminal-hub://workflow/issue"
_G_CONTEXT = "terminal-hub://workflow/context"
_G_AUTH    = "terminal-hub://workflow/auth"

_BUILTIN_COMMANDS = ["create.md", "setup.md", "auth.md", "context.md"]


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

    label_str = f"  Labels: {', '.join(labels)}" if labels else ""
    display = f"Draft saved: {title}{label_str}"
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
    display = (
        f"✓ Created #{result_dict['issue_number']} — {fm['title']}\n"
        f"  URL:   {result_dict['url']}\n"
        f"  Local: {result_dict['local_file']}"
    )
    return {**result_dict, "_display": display}


def _do_list_issues() -> dict:
    root = get_workspace_root()
    if err := ensure_initialized(root):
        return err
    return {"issues": list_issue_files(root)}


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
    if doc_key == "all":
        return {
            "project_description": read_doc_file(root, "project_description"),
            "architecture": read_doc_file(root, "architecture"),
        }
    try:
        content = read_doc_file(root, doc_key)
    except ValueError as exc:
        return {"error": "not_found", "message": str(exc), "_hook": None}
    return {"doc_key": doc_key, "content": content}


def _do_run_analyzer() -> dict:
    from plugins.github_planner.analyzer import (
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


# ── Plugin registration ───────────────────────────────────────────────────────

def register(mcp) -> None:
    """Register all GitHub-specific MCP tools and resources on the given FastMCP instance."""

    # ── Resources (workflow guides) ───────────────────────────────────────────

    @mcp.resource("terminal-hub://workflow/init")
    def workflow_init() -> str:
        """Step-by-step guide for initialising a new project workspace."""
        return _load_agent("setup.md")

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
        return _load_agent("auth.md")

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
    def list_issues() -> dict:
        """Return all tracked issues from local hub_agents/issues/ files.
        Each entry includes a 'status' field: pending | open | closed."""
        return _do_list_issues()

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
