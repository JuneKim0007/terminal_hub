"""MCP server for terminal-hub.

Registers all tools and workflow-guide resources. Entry point is create_server(),
which returns a configured FastMCP instance ready to call server.run().
"""
import json
from datetime import date
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from terminal_hub.auth import get_auth_options, resolve_token, verify_gh_cli_auth
from terminal_hub.config import WorkspaceMode, load_config, save_config
from terminal_hub.env_store import read_env, write_env
from terminal_hub.errors import msg
from terminal_hub.github_client import GitHubClient, GitHubError, load_default_labels
from terminal_hub.slugify import slugify

from terminal_hub.storage import (
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
from terminal_hub.workspace import detect_repo, init_workspace, resolve_workspace_root

_AGENTS_DIR = Path(__file__).parent.parent / "agents"

# ── Guidance URIs ─────────────────────────────────────────────────────────────
_G_INIT    = "terminal-hub://workflow/init"
_G_ISSUE   = "terminal-hub://workflow/issue"
_G_CONTEXT = "terminal-hub://workflow/context"
_G_AUTH    = "terminal-hub://workflow/auth"


def _load_agent(name: str) -> str:
    path = _AGENTS_DIR / name
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


def create_server() -> FastMCP:
    """Create and return the configured FastMCP instance."""
    mcp = FastMCP("terminal-hub", instructions=_load_agent("entry_point.md"))

    # ── Resources (workflow guides) ───────────────────────────────────────────

    @mcp.resource("terminal-hub://instructions")
    def instructions_resource() -> str:
        """Full entry point instructions and tool reference."""
        return _load_agent("entry_point.md")

    @mcp.resource("terminal-hub://workflow/init")
    def workflow_init() -> str:
        """Step-by-step guide for initialising a new project workspace."""
        return _load_agent("workflow_init.md")

    @mcp.resource("terminal-hub://workflow/issue")
    def workflow_issue() -> str:
        """Guide for creating, listing, and reloading issue context."""
        return _load_agent("workflow_issue.md")

    @mcp.resource("terminal-hub://workflow/context")
    def workflow_context() -> str:
        """Guide for loading and saving project description and architecture."""
        return _load_agent("workflow_context.md")

    @mcp.resource("terminal-hub://workflow/auth")
    def workflow_auth() -> str:
        """Auth recovery guide — check_auth → gh auth login → verify_auth."""
        return _load_agent("workflow_auth.md")

    # ── Auth tools ────────────────────────────────────────────────────────────

    @mcp.tool()
    def check_auth() -> dict:
        """Check GitHub authentication status.
        If not authenticated, presents login options to show the user.
        Call this whenever a GitHub tool returns an auth error."""
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

    @mcp.tool()
    def verify_auth() -> dict:
        """Verify GitHub CLI authentication after the user runs gh auth login.
        Call this after the user reports they have completed gh auth login."""
        success, message = verify_gh_cli_auth()
        if success:
            return {"authenticated": True, "source": "gh_cli", "message": message}
        return {
            "authenticated": False,
            "message": message,
            "options": get_auth_options(),
            "_guidance": _G_AUTH,
        }

    # ── Issue tools ───────────────────────────────────────────────────────────

    @mcp.tool()
    def draft_issue(issue_json: str) -> dict:
        """Parse a structured JSON issue draft and save it locally as status=pending.

        issue_json must be a JSON string with keys:
          title (str, required), body (str, required),
          labels (list[str], optional), assignees (list[str], optional)

        Returns {slug, title, preview_body, status} so Claude can show the user
        a preview and ask for approval before calling submit_issue.
        Local-only users can stop here — the draft is cached in hub_agents/issues/.
        """
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err

        try:
            data = json.loads(issue_json)
        except json.JSONDecodeError as exc:
            return {"error": "draft_failed", "message": msg("invalid_json", detail=str(exc)), "_hook": None}

        for field in ("title", "body"):
            if not data.get(field):
                return {"error": "draft_failed", "message": msg("missing_field", detail=field), "_hook": None}

        title: str = data["title"]
        body: str = data["body"]
        labels: list[str] = data.get("labels") or []
        assignees: list[str] = data.get("assignees") or []

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

        return {
            "slug": slug,
            "title": title,
            "preview_body": body[:300] + ("…" if len(body) > 300 else ""),
            "labels": labels,
            "assignees": assignees,
            "status": str(IssueStatus.PENDING),
            "local_file": f"hub_agents/issues/{slug}.md",
        }

    @mcp.tool()
    def submit_issue(slug: str) -> dict:
        """Submit a pending local issue draft to GitHub.

        Reads the local hub_agents/issues/<slug>.md file, bootstraps any missing
        labels, creates the GitHub issue, then updates the local file to status=open.

        Call this only after the user has approved the draft shown by draft_issue.
        On any failure Claude handles the error directly — no automatic retry.
        """
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

        return {
            "issue_number": result["number"],
            "url": result["html_url"],
            "slug": slug,
            "local_file": f"hub_agents/issues/{slug}.md",
        }

    @mcp.tool()
    def list_issues() -> dict:
        """Return all tracked issues from local hub_agents/issues/ files.
        Each entry includes a 'status' field: pending | open | closed."""
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err
        return {"issues": list_issue_files(root)}

    @mcp.tool()
    def get_issue_context(slug: str) -> dict:
        """Read a specific issue file by slug to reload context cheaply."""
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

    # ── Project context tools ─────────────────────────────────────────────────

    @mcp.tool()
    def update_project_description(content: str) -> dict:
        """Overwrite hub_agents/project_description.md.
        Call get_project_context first to preserve existing content."""
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err
        try:
            path = write_doc_file(root, "project_description", content)
            return {"updated": True, "file": str(path.relative_to(root))}
        except (OSError, ValueError) as exc:
            return {"error": "write_failed", "message": msg("write_failed", detail=str(exc)), "_hook": None}

    @mcp.tool()
    def update_architecture(content: str) -> dict:
        """Overwrite hub_agents/architecture_design.md.
        Call get_project_context first to preserve existing content."""
        root = get_workspace_root()
        if err := ensure_initialized(root):
            return err
        try:
            path = write_doc_file(root, "architecture", content)
            return {"updated": True, "file": str(path.relative_to(root))}
        except (OSError, ValueError) as exc:
            return {"error": "write_failed", "message": msg("write_failed", detail=str(exc)), "_hook": None}

    @mcp.tool()
    def get_project_context(doc_key: str) -> dict:
        """Read project_description.md and/or architecture_design.md from hub_agents/.
        doc_key: 'project_description', 'architecture', or 'all'."""
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

    # ── Workspace setup tools ─────────────────────────────────────────────────

    @mcp.tool()
    def get_setup_status() -> dict:
        """Check if this project has been initialised. Always call this first."""
        root = get_workspace_root()
        hub_dir = root / "hub_agents"
        if not hub_dir.exists():
            return {
                "initialised": False,
                "message": (
                    "hub_agents/ not found. "
                    "Ask the user if they want GitHub integration and call setup_workspace."
                ),
                "_guidance": _G_INIT,
            }
        cfg = load_config(root)
        env = read_env(root)
        return {
            "initialised": True,
            "mode": cfg["mode"] if cfg else "unknown",
            "github_repo": env.get("GITHUB_REPO"),
        }

    @mcp.tool()
    def setup_workspace(github_repo: str | None = None) -> dict:
        """Initialise terminal-hub for this project.

        Creates hub_agents/, stores github_repo in hub_agents/.env if provided,
        and gitignores hub_agents/.

        github_repo: optional 'owner/repo' — omit for local-only mode."""
        root = get_workspace_root()

        init_workspace(root)

        from terminal_hub.env_store import _ensure_gitignored
        _ensure_gitignored(root)

        values: dict[str, str] = {}
        if github_repo:
            values["GITHUB_REPO"] = github_repo
        if values:
            write_env(root, values)

        mode = WorkspaceMode.GITHUB if github_repo else WorkspaceMode.LOCAL
        save_config(root, mode, github_repo)

        label_warning: str | None = None
        if github_repo:
            gh, _ = get_github_client()
            if gh is not None:
                all_names = [d["name"] for d in load_default_labels()]
                with gh:
                    label_warning = gh.ensure_labels(all_names)

        result: dict = {
            "success": True,
            "github_repo": github_repo,
            "hub_dir": str(root / "hub_agents"),
            "message": (
                f"Initialised hub_agents/ in {root}. "
                + (f"GitHub repo set to {github_repo}." if github_repo else "Running in local-only mode.")
            ),
        }
        if label_warning:
            result["label_warning"] = label_warning
        return result

    return mcp
