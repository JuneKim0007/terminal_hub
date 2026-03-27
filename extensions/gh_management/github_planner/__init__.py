"""GitHub Planner plugin for terminal-hub.

Registers all GitHub-specific MCP tools and resources.
Call register(mcp) from create_server() to activate.
"""
# ── Re-exports for package-root importability ────────────────────────────────
from extensions.gh_management.github_planner.setup import (
    get_workspace_root,
    ensure_initialized,
    get_github_client,
    _G_INIT,
    _G_ISSUE,
    _G_CONTEXT,
    _G_AUTH,
    _BUILTIN_COMMANDS,
    _load_agent,
    _invalidate_repo_cache,
    _REPO_CACHE,
    _do_bootstrap_gh_plan,
    _do_bootstrap_new_repo,
)
# auth helpers re-exported at package root (server.py imports them here)
from extensions.gh_management.github_planner.auth import resolve_token, verify_gh_cli_auth

# Cache re-exports (used by tests/conftest.py and workspace_tools unload)
from extensions.gh_management.github_planner.analysis import (
    _ANALYSIS_CACHE,
    _FILE_TREE_CACHE,
    _DEFAULT_SCAN_PROFILE,
    _build_file_tree,
    _extract_file_index,
    _file_tree_cache_path,
    _is_markdown,
    _load_file_hashes,
    _load_scan_profile,
    _scan_profile_path,
    _should_ignore,
)
from extensions.gh_management.github_planner.project_docs import (
    _PROJECT_DOCS_CACHE,
    _SESSION_HEADER_CACHE,
    _docs_config_path,
    _gh_planner_docs_dir,
    _load_docs_config,
    _parse_h2_sections,
)
from extensions.gh_management.github_planner.labels import (
    _LABEL_CACHE,
    _LABEL_ANALYSIS_CACHE,
)
from extensions.gh_management.github_planner.milestones import (
    _MILESTONE_CACHE,
    _load_milestone_index,
    _milestone_knowledge_path,
    _milestones_dir,
)
from extensions.gh_management.github_planner.session import _SESSION_REPO_CONFIRMED
from extensions.gh_management.github_planner.skills import (
    _SKILL_REGISTRY,
    _load_skill_registry,
    _silent_skill_detection,
)
from extensions.gh_management.github_planner.issues import (
    _check_suggest_unload,
    _issues_cache_stale,
)
from extensions.gh_management.github_planner.workspace_tools import (
    _GH_PLANNER_VOLATILE_FILES,
    _load_unload_policy,
)
from extensions.gh_management.github_planner.project_docs import (
    _format_reuse_block,
    _preserve_reuse_block,
    _resolve_repo,
)
from extensions.gh_management.github_planner.milestones import (
    _ensure_milestone_label,
    _ensure_milestone_labels_for_all,
    _milestone_label_color,
    _MILESTONE_LABEL_PALETTE,
)
from extensions.gh_management.github_planner.skills import _parse_skills_dir
from extensions.gh_management.github_planner.storage import (
    write_doc_file,
    write_issue_file,
)
from extensions.gh_management.github_planner.client import create_user_repo
from terminal_hub.workspace import detect_repo
from terminal_hub.env_store import read_env
from pathlib import Path

# Plugin-level constants re-exported for patch compatibility in tests
from extensions.gh_management.github_planner.skills import (
    _PLUGIN_DIR,
    _COMMANDS_DIR,
)

# Alias for backward compat (_get_github_client was the old private name)
_get_github_client = get_github_client

# ── Domain module imports ─────────────────────────────────────────────────────
from extensions.gh_management.github_planner.session import (
    _do_confirm_session_repo,
    _do_set_session_repo,
    _do_clear_session_repo,
    _do_check_auth,
    _do_verify_auth,
)
from extensions.gh_management.github_planner.labels import (
    _do_analyze_github_labels,
    _do_load_github_local_config,
    _do_load_github_global_config,
    _do_save_github_local_config,
    _do_get_github_config,
    _do_list_repo_labels,
    _do_make_label,
)
from extensions.gh_management.github_planner.milestones import (
    _do_list_milestones,
    _do_create_milestone,
    _do_assign_milestone,
    _do_generate_milestone_knowledge,
    _do_load_milestone_knowledge,
)
from extensions.gh_management.github_planner.issues import (
    _do_draft_issue,
    _do_submit_issue,
    _do_get_issue_context,
    _do_scan_issue_context,
    _do_generate_issue_workflows,
    _do_list_issues,
    _do_list_pending_drafts,
    _do_sync_github_issues,
    _do_batch_create_issues,
)
from extensions.gh_management.github_planner.project_docs import (
    _do_update_project_description,
    _do_update_architecture,
    _do_update_project_detail_section,
    _do_update_project_summary_section,
    _do_get_project_context,
    _do_save_project_docs,
    _do_load_project_docs,
    _do_docs_exist,
    _do_lookup_feature_section,
    _do_get_session_header,
)
from extensions.gh_management.github_planner.analysis import (
    _do_run_analyzer,
    _do_get_scan_profile_status,
    _do_create_scan_profile,
    _do_start_repo_analysis,
    _do_fetch_analysis_batch,
    _do_get_analysis_status,
    _do_get_file_tree,
    _do_analyze_repo_full,
)
from extensions.gh_management.github_planner.workspace_tools import (
    _do_set_preference,
    _do_create_github_repo,
    _do_save_docs_strategy,
    _do_load_docs_strategy,
    _do_search_project_docs,
    _do_connect_docs,
    _do_load_connected_docs,
    _do_list_plugin_state,
    _do_unload_plugin,
    _do_apply_unload_policy,
    detect_existing_docs,
    _do_initialize_implementation_session,
    _do_load_implementation_context,
)
from extensions.gh_management.github_planner.skills import (
    _do_load_skill,
    _do_update_skill_detection,
    _do_update_skill_create,
    _do_update_skill,
    _do_build_docs_map,
    _do_get_docs_map,
)

# ── Plugin registration ───────────────────────────────────────────────────────

def register(mcp) -> None:
    """Register all GitHub-specific MCP tools and resources on the given FastMCP instance."""

    # ── Resources (workflow guides) ───────────────────────────────────────────

    @mcp.resource("terminal-hub://workflow/init")
    def workflow_init() -> str:
        """Step-by-step guide for initialising a new project workspace."""
        return _load_agent("gh-plan-setup.md")

    @mcp.resource("terminal-hub://workflow/issue")
    def workflow_issue() -> str:
        """Guide for creating, listing, and reloading issue context."""
        return _load_agent("gh-plan-create.md")

    @mcp.resource("terminal-hub://workflow/context")
    def workflow_context() -> str:
        """Guide for loading and saving project description and architecture."""
        return _load_agent("gh-plan.md")

    @mcp.resource("terminal-hub://workflow/auth")
    def workflow_auth() -> str:
        """Auth recovery guide — check_auth → gh auth login → verify_auth."""
        return _load_agent("gh-plan-auth.md")

    # ── Workspace root override ───────────────────────────────────────────────

    @mcp.tool()
    def set_project_root(path: str) -> dict:
        """Set the active project root so hub_agents/ is written to the user's project,
        not the MCP server's directory.

        MUST be the very first tool call in every /th: command.
        path: Claude's actual working directory (absolute path)."""
        from terminal_hub.workspace import set_active_project_root
        from terminal_hub.display import display as _text
        set_active_project_root(path)
        return {"root": str(path), "_display": _text("project_root.set", path=path)}

    # ── Session repo confirmation (#148) ──────────────────────────────────────

    @mcp.tool()
    def confirm_session_repo(force: bool = False) -> dict:
        """Check whether the current session repo has been confirmed by the user.

        Returns {confirmed, repo, _display}.
        - confirmed=True: repo is locked, proceed silently.
        - confirmed=False: Claude must show _display and ask "yes / change" before continuing.

        After user says "yes": call set_session_repo(repo=...) to lock it.
        After user says "change": let user specify repo, then call set_session_repo(repo=new).
        force=True: always re-prompt even if already confirmed.
        """
        return _do_confirm_session_repo(force)

    @mcp.tool()
    def set_session_repo(repo: str) -> dict:
        """Lock the confirmed repo for this session.

        Call after user confirms "yes" to confirm_session_repo, or after user
        specifies a replacement repo. Prevents repeated prompting this session.
        repo: 'owner/repo' string
        """
        return _do_set_session_repo(repo)

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
        agent_workflow: list[str] | None = None,
        milestone_number: int | None = None,
    ) -> dict:
        """Save an issue draft locally as status=pending.

        Returns {slug, title, status, _display, detail} — detail contains preview_body,
        labels, assignees for use when needed without cluttering terminal output.
        Local-only users can stop here — the draft is cached in hub_agents/issues/.

        note: optional meta-note about user intent or experience level — stored in
        front matter for agent reference.

        agent_workflow: ordered steps for how an agent should resolve this issue.
          Always generate this from the issue context — do NOT leave it empty.
          Steps 1-2 are standard; steps 3-N are issue-specific:
            1. Scan all files and cache the project file structure
            2. Build a temporary knowledge base — group files as relevant (Group A)
               vs unrelated (Group B)
            3. <issue-specific implementation step>
            4. <issue-specific test/verify step>
            ...
          Example for a bug fix:
            ["Scan all files and cache project structure",
             "Build knowledge base — group relevant files (Group A) vs unrelated (Group B)",
             "Reproduce the bug: identify the failing code path",
             "Fix minimally — change only what is needed",
             "Add a regression test that would have caught this",
             "Verify full test suite passes"]

        milestone_number: optional GitHub milestone number to assign (from create_milestone
          or list_milestones). Stored in front matter and passed to GitHub on submit.
        """
        return _do_draft_issue(title, body, labels, assignees, note=note, agent_workflow=agent_workflow,
                               milestone_number=milestone_number)

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
    def update_project_detail_section(
        feature_name: str,
        overview: str,
        milestone: str | None = None,
        guidelines: list[str] | None = None,
        anti_patterns: list[str] | None = None,
    ) -> dict:
        """Merge a single H2 section into project_detail.md without rewriting the full file.

        feature_name: H2 heading for this section (e.g. "Tab Navigation & Routing")
        overview: 1-3 sentence description of this feature area
        milestone: optional milestone label e.g. "M1 — Core Auth"
        guidelines: bullet-point rules for this feature (rendered as "- item")
        anti_patterns: things to avoid (rendered as "- item")

        If '## {feature_name}' already exists, replaces that section only.
        Otherwise appends a new section. Use instead of save_project_docs when
        adding/updating a single feature area to avoid accidental truncation (#65).

        Decision rule for when to call:
        - Issue labels include 'enhancement' or 'feature' → call this
        - Issue labels include 'architecture' → call this for Design Principles section
        - Labels are only 'bug', 'chore', 'refactor', 'docs' → do NOT call (no doc update)
        - No labels → ask user first"""
        return _do_update_project_detail_section(feature_name, overview, milestone, guidelines, anti_patterns)

    @mcp.tool()
    def update_project_summary_section(
        section_name: str,
        items: list[str] | None = None,
        table_rows: list[dict] | None = None,
    ) -> dict:
        """Merge a single H2 section into project_summary.md without rewriting the full file (#137).

        section_name: H2 heading (e.g. "Design Principles", "Milestones")
        items: list of bullet-point strings — use for Design Principles, feature lists, etc.
        table_rows: list of dicts for table sections — use for Milestones
                    e.g. [{"#": "M1", "Name": "Core Auth", "Delivers": "Users can sign up"}]

        If '## {section_name}' already exists, replaces that section only.
        Otherwise appends a new section. Use this to persist Milestones, Design Principles,
        or other top-level summary sections without overwriting the rest of the file.

        Primary use cases:
        - After milestone creation: section_name='Milestones', table_rows=[{"#":"M1","Name":"...","Delivers":"..."}]
        - Design principles: section_name='Design Principles', items=["No global state", ...]
        - When project goals change: update the relevant section only"""
        return _do_update_project_summary_section(section_name, items, table_rows)

    @mcp.tool()
    def update_project_description(title: str, description: str, notes: str = "") -> dict:
        """Overwrite hub_agents/project_description.md with structured fields.

        title: project name
        description: 1-3 sentence project overview
        notes: optional constraints or deployment notes
        Call get_project_context first to preserve existing content."""
        return _do_update_project_description(title, description, notes)

    @mcp.tool()
    def update_architecture(overview: str, components: list[str] | None = None, notes: str = "") -> dict:
        """Overwrite hub_agents/architecture_design.md with structured fields.

        overview: 1-3 sentence architecture summary
        components: list of key components (rendered as bullet list)
        notes: optional notes
        Call get_project_context first to preserve existing content."""
        return _do_update_architecture(overview, components, notes)

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

    @mcp.tool()
    def search_project_docs() -> dict:
        """Search the project for useful .md documentation files to connect as references (#164).

        Returns a ranked list of candidates with path, size_kb, and headings.
        Use with connect_docs() to set a primary reference."""
        return _do_search_project_docs()

    @mcp.tool()
    def connect_docs(
        primary: str | None = None,
        detail: str | None = None,
        skills: str | None = None,
        others: list[str] | None = None,
    ) -> dict:
        """Connect existing project docs as references for planning and implementation (#164).

        primary: path (relative to project root) to the primary summary doc (default: hub_agents/project_summary.md)
        detail: path to the detail doc (default: hub_agents/project_detail.md)
        skills: path to a SKILLS.md index file for Tier 2 project skills
        others: list of paths to additional reference docs
        Saved to hub_agents/extensions/gh_planner/docs_config.json."""
        return _do_connect_docs(primary, detail, skills, others)

    @mcp.tool()
    def load_connected_docs(section: str | None = None) -> dict:
        """Load the primary connected reference doc (or a specific section from it) (#164).

        section: optional H2 heading name to extract a specific section.
        Call connect_docs() first to set a primary reference.
        Returns {content, path}."""
        return _do_load_connected_docs(section)

    @mcp.tool()
    def load_skill(name: str) -> dict:
        """Load a skill file from the registry by name.

        Searches Tier 1 (plugin skills at extensions/gh_management/github_planner/skills/)
        and Tier 2 (project skills from docs_config["skills"] path).
        Tier 2 overrides Tier 1 on name collision.

        name: skill name (e.g. 'creating-issues', 'plugin-architecture')
        Returns {name, content, tier, _display} or {error, available}.
        """
        return _do_load_skill(name)

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
    def save_project_docs(
        goal: str,
        tech_stack: list[str],
        notes: str = "",
        design_principles: list[str] | None = None,
        repo: str | None = None,
    ) -> dict:
        """Initialise project_summary.md with structured fields — no raw markdown blobs.

        goal: one-sentence description of what the project does
        tech_stack: list of framework/language names e.g. ["React 19", "TypeScript", "Vite"]
        notes: optional deployment/constraint note (short string)
        design_principles: list of architectural rules e.g. ["No global state", "Color tokens only"]

        After calling this, use update_project_summary_section() to add further H2 sections
        (Milestones, Feature Sections, etc.) and update_project_detail_section() for per-feature notes.
        """
        return _do_save_project_docs(goal, tech_stack, notes, design_principles, repo)

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

    @mcp.tool()
    def scan_issue_context(feature_areas: list[str]) -> dict:
        """Scan project_detail.md sections for code references relevant to feature_areas.

        For each area, looks up the matching section and parses it for function/class
        definitions, file paths, and pitfall warnings.

        Returns:
          {reusable: [{name, path, description}], extend: [], patterns: [str],
           pitfalls: [str], sections_scanned: [str]}

        Call before drafting an issue when project_detail.md has relevant sections.
        Use findings to populate agent_workflow steps with explicit file and function references.
        """
        return _do_scan_issue_context(feature_areas)

    @mcp.tool()
    def update_skill(
        name: str | None = None,
        description: str | None = None,
        content_hints: list[str] | None = None,
        source_doc: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Detect knowledge that should be a skill, or create a new skill file.

        Detection mode (name=None): scans command files and open issues for
        inline knowledge blocks > 50 lines or domain clusters with no skill.
        Returns candidate list. Prompts user to create skill files.

        Creation mode (name provided): creates skill file using create-skill.md
        authoring rules, updates SKILLS.md registry, optionally extracts from
        source_doc and replaces with <!-- SKILL: load_skill("name") --> comment.

        Returns {name, path, registry_updated, source_doc_updated, dry_run, _display}
        or {candidates, message} in detection mode.
        """
        return _do_update_skill(name, description, content_hints, source_doc, dry_run)

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

        Common command values: 'gh-plan', 'gh-plan-analyze',
        'gh-plan-create', 'gh-plan-unload', 'create-github-repo'.
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

    @mcp.tool()
    def list_repo_labels() -> dict:
        """Fetch all labels from the GitHub repo and cache them locally.

        Call before draft_issue to know which labels are available.
        Returns {labels, names, count}. Returns from cache if available."""
        return _do_list_repo_labels()

    @mcp.tool()
    def get_scan_profile_status() -> dict:
        """Check if hub_agents/scan_profile.yaml exists.

        Returns {exists, needs_creation, profile, _display}.
        If needs_creation=true, print _display and ask user to create it before analyzing.
        Call this at the start of gh-plan-analyze before running analysis.
        """
        return _do_get_scan_profile_status()

    @mcp.tool()
    def create_scan_profile(content: str | None = None) -> dict:
        """Create hub_agents/scan_profile.yaml.

        content: optional custom YAML string. If omitted, writes the default profile.
        Default includes common code/doc extensions, excludes node_modules/.git/venv/etc.
        """
        return _do_create_scan_profile(content)

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

    @mcp.tool()
    def list_milestones(state: str = "open") -> dict:
        """List GitHub milestones. Uses in-memory cache if populated — no API call needed.

        If _MILESTONE_CACHE is populated for this repo, return cached data directly.
        Only call this when you genuinely don't know the current milestones.
        state: 'open' | 'closed' | 'all'
        """
        return _do_list_milestones(state)

    @mcp.tool()
    def create_milestone(title: str, description: str = "", due_on: str | None = None) -> dict:
        """Create a GitHub milestone (idempotent — returns existing if title already taken).

        **Convention:** Only create a milestone when a coherent group of related features
        warrants a named release phase — typically >= 3 issues with a shared theme.
        Name pattern: descriptive theme (e.g. "Core Auth", "Posting & Feed", "Launch Polish").
        Avoid generic names like "Milestone 1" or "Phase A".

        **Auto-label:** After creation, a milestone label `m{N}` is automatically created
        on GitHub and synced to labels.json so issues can be tagged by milestone.

        title: short descriptive theme (e.g. "Core Auth")
        description: one sentence — what the user can do after this milestone ships
        due_on: optional ISO 8601 date string (e.g. '2026-04-01T00:00:00Z')
        """
        return _do_create_milestone(title, description, due_on)

    @mcp.tool()
    def assign_milestone(slug: str, milestone_number: int) -> dict:
        """Assign a milestone to a local issue and update GitHub if the issue is submitted.

        slug: local issue slug (e.g. '1', 'fix-auth-bug')
        milestone_number: GitHub milestone number (from create_milestone or list_milestones)

        Updates both local front matter and GitHub. Idempotent — safe to call multiple times.
        """
        return _do_assign_milestone(slug, milestone_number)

    @mcp.tool()
    def generate_milestone_knowledge(milestone_number: int) -> dict:
        """Generate a structured knowledge file for a milestone at hub_agents/milestones/M{n}.md.

        Reads milestone details from _MILESTONE_CACHE and project docs from _PROJECT_DOCS_CACHE.
        Writes a structured markdown file covering: Goal, Features Governed, Interface Contract,
        Depends On, Enables, and Design Principles Applicable.

        Also updates milestone_index.json, syncs project_summary.md Milestones table,
        and updates Enables/Depends On links in adjacent milestone knowledge files.

        milestone_number: GitHub milestone number (e.g. 1, 2, 3)
        """
        return _do_generate_milestone_knowledge(milestone_number)

    @mcp.tool()
    def load_milestone_knowledge(milestone_number: int) -> dict:
        """Load the knowledge file for a milestone from hub_agents/milestones/M{n}.md.

        Returns {milestone_number, content, exists, _display}.
        If the file does not exist, returns exists=False with instructions to generate it.

        milestone_number: GitHub milestone number (e.g. 1, 2, 3)
        """
        return _do_load_milestone_knowledge(milestone_number)

    @mcp.tool()
    def build_docs_map() -> dict:
        """Scan plugin skills and command files, build docs_map.json in the plugin directory.

        Extracts: skill metadata (alwaysApply, triggers), which commands load each skill
        (via load_skill() calls), and which MCP tools each command references.
        Writes results to extensions/gh_management/github_planner/docs_map.json.
        Returns {skills, commands, _display}.
        """
        return _do_build_docs_map()

    @mcp.tool()
    def get_docs_map(view: str = "skills") -> dict:
        """Read docs_map.json and return a formatted table.

        Rebuilds docs_map.json automatically if not present.

        view: "skills" — shows all skills, which commands load them, alwaysApply, triggers
              "commands" — shows all commands, skills they load, MCP tools they reference
        Returns {view, data, _display}.
        """
        return _do_get_docs_map(view)

    # ── Integrated flow tools (#218) ───────────────────────────────────────────

    @mcp.tool()
    def bootstrap_gh_plan(project_root: str, confirm_repo: bool = True, sync_issues: bool = True, full_data: bool = False) -> dict:
        """Bootstrap gh-plan in one call: set root, confirm repo, warm milestones, sync and list issues.

        Replaces the 8-call gh-plan startup sequence with a single atomic operation.

        project_root: absolute path to the project directory
        confirm_repo: if False, skip repo confirmation (already confirmed this session)
        sync_issues: if False, skip GitHub sync (use cached issues)
        full_data: if True, include full issue objects in response (default False — returns issue_slugs only)
        Returns {workspace_ready, confirmed_repo, milestones, sync_result, issue_slugs, issue_count, landscape_display, _display}
        When full_data=True also returns: {issues}
        """
        return _do_bootstrap_gh_plan(project_root, confirm_repo, sync_issues, full_data)

    @mcp.tool()
    def batch_create_issues(issue_specs: list, confirm_before_submit: bool = True) -> dict:
        """Draft and optionally submit multiple issues in one call.

        Replaces the label-warm + draft×N + submit×N sequence for Step 6g.

        issue_specs: list of {title, body, labels, assignees, agent_workflow, milestone_number}
        confirm_before_submit: if True (default), only drafts — Claude calls submit_issue() after user confirms
        Returns {drafts, validation_errors, confirmation_display, submitted, failed_submissions, all_succeeded, _display}
        """
        return _do_batch_create_issues(issue_specs, confirm_before_submit)

    @mcp.tool()
    def initialize_implementation_session(project_root: str, previous_command: str = "gh-plan") -> dict:
        """Initialize gh-implementation session in one call.

        Replaces the 7-call startup sequence: unload previous command, confirm repo,
        load project docs, and list issues.

        project_root: absolute path to the project
        previous_command: command to unload (default: 'gh-plan')
        Returns {workspace_ready, cache_cleared, repo_confirmed, project_summary, issues, issue_count, next_action, _display}
        """
        return _do_initialize_implementation_session(project_root, previous_command)

    @mcp.tool()
    def load_implementation_context(project_root: str, issue_slug: str, lookup_design_refs: bool = True) -> dict:
        """Load full implementation context in one call.

        Replaces 8-call sequence: initialize session + load active issue + design ref sections.

        project_root: absolute path to project
        issue_slug: issue slug to load (e.g. '42')
        lookup_design_refs: if True, load design_ref sections from project_detail.md
        Returns {workspace_ready, repo_confirmed, project_summary, issue_content, design_sections, has_agent_workflow, context_ready, _display}
        """
        return _do_load_implementation_context(project_root, issue_slug, lookup_design_refs)

    @mcp.tool()
    def bootstrap_new_repo(
        project_title: str,
        project_description: str,
        tech_stack: list,
        design_principles: list,
        is_private: bool = True,
        confirm_arch_changes: bool = False,
    ) -> dict:
        """Create a new GitHub repo and fully bootstrap the workspace in one call.

        Replaces the 11-call new-repo path sequence.

        project_title: name for the new repo
        project_description: one-sentence description
        tech_stack: list of tech stack items
        design_principles: list of initial design principles
        is_private: create as private repo (default: True)
        confirm_arch_changes: persist confirm_arch_changes preference (default: False)
        Returns {project_description_saved, repo_created, repo_url, workspace_linked, caches_warmed, ready_to_plan, _display}
        """
        return _do_bootstrap_new_repo(project_title, project_description, tech_stack, design_principles, is_private, confirm_arch_changes)
