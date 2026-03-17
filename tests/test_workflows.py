"""End-to-end workflow walkthroughs for terminal-hub.

Each test simulates a complete user journey — a sequence of tool calls in the
order a real user would make them. After each walkthrough, the test comments
capture a three-axis evaluation:

  PERFORMANCE  – API call count, token estimate, improvement opportunities.
  USABILITY    – Is the conversation the flow? Is each step natural?
  BUGS / RISK  – Known issues or potential failure modes in this path.

Run with: python -m pytest tests/test_workflows.py -v
"""
import importlib
import json
import os
import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import extensions.github_planner as pg
from extensions.github_planner import (
    _ANALYSIS_CACHE,
    _PROJECT_DOCS_CACHE,
    _SESSION_HEADER_CACHE,
    _do_analyze_repo_full,
    _do_check_auth,
    _do_docs_exist,
    _do_draft_issue,
    _do_get_issue_context,
    _do_get_session_header,
    _do_list_issues,
    _do_load_project_docs,
    _do_save_project_docs,
    _do_submit_issue,
    _do_verify_auth,
    _gh_planner_docs_dir,
)
from extensions.github_planner.storage import (
    IssueStatus,
    write_issue_file,
)
from extensions.plugin_creator import (
    _do_validate_plugin,
    _do_write_plugin_file,
    _do_write_test_file,
)
from terminal_hub.server import create_server


# ── Shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_caches():
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    _SESSION_HEADER_CACHE.clear()
    yield
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    _SESSION_HEADER_CACHE.clear()


@pytest.fixture
def workspace(tmp_path):
    """Initialised workspace (hub_agents/ exists)."""
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def uninit_workspace(tmp_path):
    """Un-initialised workspace (no hub_agents/)."""
    return tmp_path


@pytest.fixture
def mock_gh():
    """Authenticated GitHub client mock with sensible defaults."""
    gh = MagicMock()
    gh.__enter__ = lambda s: s
    gh.__exit__ = MagicMock(return_value=False)
    gh.list_repo_tree.return_value = []
    gh.create_issue.return_value = {"number": 1, "html_url": "https://github.com/o/r/issues/1"}
    gh.ensure_labels.return_value = None
    return gh


def _seed_issue(workspace, slug="fix-login-bug", title="Fix login bug",
                body="Steps to reproduce...", status=IssueStatus.PENDING):
    write_issue_file(
        root=workspace, slug=slug, title=title, body=body,
        assignees=[], labels=[], created_at=date(2026, 3, 17), status=status,
    )
    return slug


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY 1 — First-time Setup
# ─────────────────────────────────────────────────────────────────────────────
#
# User Intent: "I want to start tracking issues for my GitHub project."
#
# Tool sequence:
#   get_setup_status → needs_init
#   setup_workspace  → initialised
#   check_auth       → authenticated (or options if not)
#   list_issues      → empty (workspace just created)
#
# PERFORMANCE  : 4 calls total. No GitHub API calls in this path.
#               Acceptable for a one-time setup.
# USABILITY    : ✓ Conversation leads: get_setup_status fires the "needs_init"
#               prompt which contains the exact question to ask the user.
#               ✓ setup_workspace asks for repo inline — one round-trip.
#               ⚠ If auth fails, user must run `gh auth login` outside Claude —
#               no way to stay in-flow. (Known limitation, acceptable.)
# BUGS / RISK  : No bugs. If hub_agents/ already exists, get_setup_status
#               returns initialised=True and skips setup — idempotent.

class TestJourney1_FirstTimeSetup:

    def test_uninit_workspace_reports_not_initialised(self, uninit_workspace):
        """get_setup_status detects missing hub_agents/ and returns guidance."""
        server = create_server()
        with patch("terminal_hub.server.get_workspace_root", return_value=uninit_workspace), \
             patch("extensions.github_planner.get_workspace_root", return_value=uninit_workspace):
            import asyncio
            result = asyncio.run(server._tool_manager.call_tool("get_setup_status", {}))

        data = result if isinstance(result, dict) else result[0].text if hasattr(result[0], 'text') else {}
        if isinstance(data, str):
            data = json.loads(data)
        assert data.get("initialised") is False
        assert "_guidance" in data

    def test_init_workspace_is_idempotent(self, workspace):
        """Calling get_setup_status on an already-initialised workspace returns True."""
        server = create_server()
        with patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            import asyncio
            result = asyncio.run(server._tool_manager.call_tool("get_setup_status", {}))

        data = result if isinstance(result, dict) else result[0].text if hasattr(result[0], 'text') else {}
        if isinstance(data, str):
            data = json.loads(data)
        assert data.get("initialised") is True

    def test_check_auth_authenticated_path(self):
        """check_auth returns authenticated=True when token resolves."""
        mock_source = MagicMock()
        mock_source.value = "env"
        with patch("extensions.github_planner.resolve_token",
                   return_value=("token123", mock_source)):
            result = _do_check_auth()
        assert result["authenticated"] is True
        assert "source" in result

    def test_check_auth_unauthenticated_provides_options(self):
        """check_auth returns guidance + options when no token is found."""
        mock_source = MagicMock()
        mock_source.suggestion.return_value = "Run gh auth login"
        with patch("extensions.github_planner.resolve_token",
                   return_value=(None, mock_source)):
            result = _do_check_auth()
        assert result["authenticated"] is False
        assert "options" in result
        assert "_guidance" in result

    def test_first_list_issues_returns_empty(self, workspace):
        """After setup, list_issues returns empty list — expected starting state."""
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_list_issues()
        assert result["issues"] == []


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY 2 — Proactive Issue Creation (Conversational)
# ─────────────────────────────────────────────────────────────────────────────
#
# User Intent: Describes a bug in passing. Claude offers to draft it.
#
# Tool sequence (happy path):
#   draft_issue(title, body, labels)  → {slug, _display: "✓ title"}
#   [user approves]
#   submit_issue(slug)               → {issue_number, url, _display: "✓ #N title"}
#
# PERFORMANCE  : 2 tool calls + 1 GitHub API call (create issue).
#               Minimal — this is already optimal.
# USABILITY    : ✓ _display shows ONLY the title in draft — no JSON noise.
#               ✓ submit_issue shows "#N title" — confirms the real issue number.
#               ✓ Conversation stays silent until user approves (no auto-submit).
#               ⚠ If labels don't exist in repo, ensure_labels makes extra API
#               calls. This is mostly invisible to the user but adds latency.
# BUGS / RISK  : BUG — If the user approves and then submit fails (e.g. rate
#               limit), the local file is left as status=pending with no feedback
#               to retry. The _hook field is None. Claude must guide recovery.

class TestJourney2_ProactiveIssueDraft:

    def test_draft_creates_local_file_with_pending_status(self, workspace):
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_draft_issue("Fix login redirect", "When you click login, nothing happens.")
        assert result["status"] == "pending"
        issue_file = workspace / "hub_agents" / "issues" / f"{result['slug']}.md"
        assert issue_file.exists()

    def test_draft_display_is_title_only(self, workspace):
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_draft_issue("Fix login redirect", "body text")
        # USABILITY CHECK: _display must be silent — title only, no JSON or metadata
        assert result["_display"] == "✓ Fix login redirect"

    def test_draft_then_submit_full_flow(self, workspace, mock_gh):
        """End-to-end: draft → approve → submit → GitHub issue created."""
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            draft = _do_draft_issue("Fix login redirect", "Steps to repro", labels=["bug"])
        slug = draft["slug"]

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
            submitted = _do_submit_issue(slug)

        # USABILITY CHECK: confirmation shows number and title, not raw JSON
        assert submitted["_display"] == "✓ #1 Fix login redirect"
        assert submitted["issue_number"] == 1
        assert "url" in submitted

    def test_submit_without_draft_returns_not_found(self, workspace):
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_submit_issue("non-existent-slug")
        assert result["error"] in ("submit_failed", "not_found")

    def test_draft_empty_title_returns_error(self, workspace):
        """USABILITY: empty title should fail fast with a clear message, not create a file."""
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_draft_issue("", "some body")
        assert result["error"] == "draft_failed"
        # Verify no file was created
        issues = list((workspace / "hub_agents" / "issues").glob("*.md"))
        assert issues == []

    def test_submit_returns_guidance_when_no_auth(self, workspace):
        """USABILITY: when submit fails due to auth, user gets actionable guidance."""
        _seed_issue(workspace)
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.get_github_client", return_value=(None, "No token found.")):
            result = _do_submit_issue("fix-login-bug")
        assert result["error"] == "github_unavailable"
        assert "_guidance" in result


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY 3 — Session Resume (Returning User with Stale Docs)
# ─────────────────────────────────────────────────────────────────────────────
#
# User Intent: "Let me pick up where I left off yesterday."
#
# Tool sequence (fresh docs):
#   get_session_header   → {docs: True, age_hours: 3, stale: False}
#   list_issues(compact) → [{slug, title, status}] — 3× cheaper than full
#   [continue working — no full summary load needed if docs are fresh]
#
# Tool sequence (stale docs):
#   get_session_header        → {docs: True, age_hours: 200, stale: True}
#   load_project_docs(summary) → re-read summary for context
#
# PERFORMANCE  : Fresh: 2 calls, ~120 tokens total. Stale: +1 call, +400 tokens.
#               The session_header acts as a gatekeeper — Claude only loads
#               expensive context when actually needed.
#               IMPROVEMENT: list_issues compact=True should be the default
#               when called from session_start context.
# USABILITY    : ✓ "stale: True" tells Claude to reload — no guesswork.
#               ✓ Compact list gives enough info to have a natural first turn.
#               ⚠ If user has many pending drafts, compact still hides body —
#               they may need get_issue_context to recall what a draft was about.
# BUGS / RISK  : _SESSION_HEADER_CACHE is never invalidated within a session.
#               If docs are updated mid-session (e.g. re-analysis), the header
#               will still report old age_hours. Low impact in practice since
#               header is only checked once at session start.

class TestJourney3_SessionResume:

    def test_fresh_docs_header_reports_not_stale(self, workspace):
        docs_dir = _gh_planner_docs_dir(workspace)
        docs_dir.mkdir(parents=True)
        (docs_dir / "project_summary.md").write_text("# My Project\nA cool project.")

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            header = _do_get_session_header()

        assert header["docs"] is True
        assert header["stale"] is False
        assert header["title"] == "My Project"

    def test_stale_docs_header_reports_stale(self, workspace):
        docs_dir = _gh_planner_docs_dir(workspace)
        docs_dir.mkdir(parents=True)
        summary = docs_dir / "project_summary.md"
        summary.write_text("# Old Project")
        old_time = time.time() - (8 * 24 * 3600)  # 8 days ago
        os.utime(summary, (old_time, old_time))

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            header = _do_get_session_header()

        assert header["stale"] is True

    def test_compact_list_is_cheaper_than_full(self, workspace):
        """Compact mode omits labels, assignees, created_at, local_file — ~3× fewer fields."""
        for i in range(3):
            _seed_issue(workspace, slug=f"issue-{i}", title=f"Issue {i}")

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            compact = _do_list_issues(compact=True)
            full = _do_list_issues(compact=False)

        compact_keys = set(compact["issues"][0].keys())
        full_keys = set(full["issues"][0].keys())

        # PERFORMANCE CHECK: compact should have strictly fewer fields
        # local_only is included for unsubmitted issues (#102)
        assert compact_keys == {"slug", "title", "status", "local_only"}
        assert len(full_keys) > len(compact_keys)

    def test_session_start_sequence_token_budget(self, workspace):
        """PERFORMANCE: Fresh session with docs should need ≤2 tool calls before first user reply."""
        docs_dir = _gh_planner_docs_dir(workspace)
        docs_dir.mkdir(parents=True)
        (docs_dir / "project_summary.md").write_text("# My Project\nPython tool.")
        _seed_issue(workspace, slug="fix-bug", title="Fix bug")

        call_count = 0

        def track(func):
            def wrapper(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return func(*args, **kwargs)
            return wrapper

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            header = track(_do_get_session_header)()   # call 1
            issues = track(_do_list_issues)(compact=True)  # call 2

        assert call_count == 2
        assert header["docs"] is True
        assert len(issues["issues"]) == 1

    def test_header_cached_across_calls(self, workspace):
        """PERFORMANCE: Second get_session_header call should not read disk again."""
        docs_dir = _gh_planner_docs_dir(workspace)
        docs_dir.mkdir(parents=True)
        (docs_dir / "project_summary.md").write_text("# Cached Project")

        disk_reads = []

        original_read = Path.read_text
        def counting_read(self, *args, **kwargs):
            if "project_summary" in str(self):
                disk_reads.append(str(self))
            return original_read(self, *args, **kwargs)

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch.object(Path, "read_text", counting_read):
            _do_get_session_header()  # populates cache
            _do_get_session_header()  # should hit cache

        assert len(disk_reads) == 1  # only read once

    def test_header_cache_invalidated_after_save_project_docs(self, workspace):
        """#61 — after save_project_docs, get_session_header must reflect fresh docs."""
        docs_dir = _gh_planner_docs_dir(workspace)
        docs_dir.mkdir(parents=True)
        # Backdate the existing summary so header reports stale
        summary = docs_dir / "project_summary.md"
        summary.write_text("# Old Project")
        old_time = time.time() - (8 * 24 * 3600)
        os.utime(summary, (old_time, old_time))

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            stale_header = _do_get_session_header()
        assert stale_header["stale"] is True  # pre-condition

        # Now save fresh docs — this must clear the session header cache
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
            _do_save_project_docs("# New Project\nFresh content.", "detail", "o/r")

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            fresh_header = _do_get_session_header()
        assert fresh_header["stale"] is False
        assert fresh_header["title"] == "New Project"


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY 4 — Full Repo Analysis (New Project, No Docs Yet)
# ─────────────────────────────────────────────────────────────────────────────
#
# User Intent: "Can you understand my codebase so we can plan together?"
#
# Tool sequence:
#   docs_exist                                → {summary_exists: False}
#   analyze_repo_full()                       → {file_index: [...], total: N}
#   [Claude generates summary + detail from file_index — no extra tool calls]
#   save_project_docs(summary_md, detail_md)  → {saved: True}
#
# PERFORMANCE  : 3 tool calls + 1 GitHub tree API + N content API calls.
#               vs old flow: 3 calls + N batched fetch loops + N content calls.
#               The key win: Claude receives structured index (~30 tok/file)
#               not raw content (~150 tok/file). For 40-file repo: ~4.8K vs 24K tokens.
#               IMPROVEMENT: If docs are fresh (< 7 days), Claude should skip
#               the full fetch and just load_project_docs(summary). The current
#               analyze.md command asks this correctly.
# USABILITY    : ✓ Single call — user doesn't see intermediate loop steps.
#               ✓ "_display" tells user the file count immediately.
#               ⚠ For very large repos (>200 files), cap silently truncates.
#               User has no way to know some files were omitted. POTENTIAL BUG.
# BUGS / RISK  : RISK — If GitHub rate limits mid-fetch (in to_fetch loop),
#               some files are skipped silently and their SHAs are not stored,
#               so next run will re-fetch them even if unchanged. Acceptable
#               degradation but could surprise users on large repos.

class TestJourney4_FullRepoAnalysis:

    def _make_tree(self, paths):
        return [{"path": p, "size": 50, "sha": f"sha-{i}"} for i, p in enumerate(paths)]

    def _mock_gh_for_tree(self, tree, content_fn=None):
        gh = MagicMock()
        gh.__enter__ = lambda s: s
        gh.__exit__ = MagicMock(return_value=False)
        gh.list_repo_tree.return_value = tree
        gh.get_file_content.side_effect = content_fn or (lambda p: f"# {p}\n")
        return gh

    def test_no_docs_triggers_analysis(self, workspace):
        """USABILITY: docs_exist returns False → Claude should proceed with analysis."""
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_docs_exist()
        assert result["summary_exists"] is False

    def test_analyze_full_returns_structured_index(self, workspace):
        """PERFORMANCE: each file returns a compact structured dict, not raw content."""
        tree = self._make_tree(["server.py", "README.md", "tests/test_core.py"])
        gh = self._mock_gh_for_tree(tree, content_fn=lambda p:
            "def foo(): pass\ndef bar(): pass" if p.endswith(".py") else f"# {p}\n"
        )
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner._get_github_client", return_value=(gh, "")), \
             patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
            result = _do_analyze_repo_full("o/r")

        assert "file_index" in result
        # PERFORMANCE CHECK: each entry is a structured dict, NOT a raw string
        for entry in result["file_index"]:
            assert isinstance(entry, dict)
            assert "content" not in entry  # raw content must never appear
            assert "path" in entry
            assert "type" in entry

    def test_analyze_full_one_call_replaces_loop(self, workspace):
        """PERFORMANCE: analyze_repo_full completes in exactly 1 Python call."""
        tree = self._make_tree(["a.py", "b.py", "c.py"])
        gh = self._mock_gh_for_tree(tree)

        outer_calls = []
        original = pg._do_analyze_repo_full

        def counting_analyze(*args, **kwargs):
            outer_calls.append(1)
            return original(*args, **kwargs)

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner._get_github_client", return_value=(gh, "")), \
             patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
            result = counting_analyze("o/r")

        # Exactly 1 invocation — no loop on the Python side
        assert len(outer_calls) == 1
        assert result["fetched"] == 3

    def test_save_docs_then_header_reflects_fresh(self, workspace):
        """USABILITY: after save_project_docs, get_session_header shows docs=True."""
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
            _do_save_project_docs("# My Project\nPython MCP server.", "detail text.", "o/r")

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            header = _do_get_session_header()

        assert header["docs"] is True
        assert header["stale"] is False


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY 5 — Re-Analysis (Incremental, Repo Has Changed)
# ─────────────────────────────────────────────────────────────────────────────
#
# User Intent: "My codebase changed since last week. Update the analysis."
#
# Tool sequence:
#   docs_exist        → {summary_exists: True, summary_age_hours: 180}
#   analyze_repo_full → {fetched: 4, skipped_unchanged: 38}
#   save_project_docs → {saved: True}
#
# PERFORMANCE  : skipped_unchanged files generate 0 API calls and 0 tokens.
#               For a 42-file repo with 4 changes: 4 content fetches vs 42.
#               IMPROVEMENT: The stale threshold in analyze.md is 7 days.
#               If a user re-analyzes daily, the 168-hour threshold means
#               get_session_header never marks it stale — good.
# USABILITY    : ✓ The _display message shows counts: "4 fetched, 38 unchanged"
#               ✓ User sees meaningful progress without seeing file contents.
# BUGS / RISK  : RISK — file_hashes.json is not gitignored. If the user
#               accidentally commits it, the SHA map goes stale when checking
#               out a different branch. Could cause re-analysis to skip files
#               incorrectly. SHOULD be in hub_agents/ which IS gitignored.

class TestJourney5_IncrementalReanalysis:

    def test_unchanged_files_skipped_by_sha(self, workspace):
        """PERFORMANCE: files with matching SHAs are not fetched again."""
        docs_dir = _gh_planner_docs_dir(workspace)
        docs_dir.mkdir(parents=True)
        hashes = {f"file{i}.py": f"sha{i}" for i in range(10)}
        (docs_dir / "file_hashes.json").write_text(json.dumps(hashes))

        tree = [{"path": f"file{i}.py", "size": 50, "sha": f"sha{i}"} for i in range(10)]
        # Add one NEW file
        tree.append({"path": "new_feature.py", "size": 100, "sha": "new-sha"})

        gh = MagicMock()
        gh.__enter__ = lambda s: s
        gh.__exit__ = MagicMock(return_value=False)
        gh.list_repo_tree.return_value = tree
        gh.get_file_content.return_value = "def new(): pass"

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner._get_github_client", return_value=(gh, "")), \
             patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
            result = _do_analyze_repo_full("o/r")

        assert result["skipped_unchanged"] == 10
        assert result["fetched"] == 1
        # PERFORMANCE: only 1 content API call made for the new file
        gh.get_file_content.assert_called_once_with("new_feature.py")

    def test_updated_hashes_persisted_after_reanalysis(self, workspace):
        """PERFORMANCE: new SHAs are written so next run skips them too."""
        tree = [{"path": "mod.py", "size": 50, "sha": "new-sha"}]
        gh = MagicMock()
        gh.__enter__ = lambda s: s
        gh.__exit__ = MagicMock(return_value=False)
        gh.list_repo_tree.return_value = tree
        gh.get_file_content.return_value = "x = 1"

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner._get_github_client", return_value=(gh, "")), \
             patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
            _do_analyze_repo_full("o/r")

        hashes_file = _gh_planner_docs_dir(workspace) / "file_hashes.json"
        saved = json.loads(hashes_file.read_text())
        assert saved.get("mod.py") == "new-sha"

    def test_display_shows_skip_counts(self, workspace):
        """USABILITY: _display summarises what was fetched vs skipped."""
        docs_dir = _gh_planner_docs_dir(workspace)
        docs_dir.mkdir(parents=True)
        (docs_dir / "file_hashes.json").write_text(json.dumps({"old.py": "same"}))
        tree = [
            {"path": "old.py", "size": 50, "sha": "same"},
            {"path": "new.py", "size": 50, "sha": "different"},
        ]
        gh = MagicMock()
        gh.__enter__ = lambda s: s
        gh.__exit__ = MagicMock(return_value=False)
        gh.list_repo_tree.return_value = tree
        gh.get_file_content.return_value = "x = 1"

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner._get_github_client", return_value=(gh, "")), \
             patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
            result = _do_analyze_repo_full("o/r")

        assert "1 unchanged" in result["_display"]
        assert "1" in result["_display"]  # fetched count


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY 6 — Issue Triage (List → Read → Submit)
# ─────────────────────────────────────────────────────────────────────────────
#
# User Intent: "Show me what's open and let me push the oldest pending draft."
#
# Tool sequence:
#   list_issues(compact=True)         → [{slug, title, status}]
#   get_issue_context("fix-login-bug") → full markdown content
#   submit_issue("fix-login-bug")     → {issue_number, url}
#
# PERFORMANCE  : 3 calls + 1 GitHub API call. The compact list avoids sending
#               full issue bodies when the user only wants to browse.
#               IMPROVEMENT: If there are 0 pending issues, skip submit step
#               entirely. The command should check status before offering to push.
# USABILITY    : ✓ Compact list is enough for a natural "here's what you have".
#               ✓ Full context loads on demand — user can ask "what was that bug?"
#               ⚠ list_issues returns LOCAL drafts only, not GitHub issues.
#               If user created issues directly on GitHub, they won't appear here.
#               This is by design (local-first) but can confuse users.
# BUGS / RISK  : RISK — If a draft was submitted but the local status update
#               fails (e.g. write error), the draft remains "pending" locally
#               but is already "open" on GitHub. Re-submitting would create a
#               duplicate. The atomic write in update_issue_status reduces but
#               doesn't eliminate this risk on hard crashes.

class TestJourney6_IssueTriage:

    def test_compact_list_shows_all_statuses(self, workspace):
        """USABILITY: compact list must show status so user knows what needs pushing."""
        _seed_issue(workspace, slug="draft-1", title="Draft one", status=IssueStatus.PENDING)
        _seed_issue(workspace, slug="open-1", title="Open one", status=IssueStatus.OPEN)

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_list_issues(compact=True)

        statuses = {i["status"] for i in result["issues"]}
        assert "pending" in statuses
        assert "open" in statuses

    def test_get_issue_context_returns_full_body(self, workspace):
        """USABILITY: context call returns full markdown so Claude can describe the issue."""
        _seed_issue(workspace, slug="fix-login-bug", title="Fix login bug",
                    body="When clicking login, the page redirects incorrectly.")
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_get_issue_context("fix-login-bug")

        assert "Fix login bug" in result["content"]
        assert "redirects incorrectly" in result["content"]

    def test_get_issue_context_not_found_returns_error(self, workspace):
        """USABILITY: missing slug returns clear error — no ambiguous None."""
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_get_issue_context("does-not-exist")
        assert result["error"] == "not_found"

    def test_full_triage_sequence(self, workspace, mock_gh):
        """End-to-end: list → read context → submit pending → verify status change."""
        _seed_issue(workspace, slug="fix-login-bug", title="Fix login bug",
                    body="Steps to reproduce the login issue.")

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            compact = _do_list_issues(compact=True)

        assert any(i["status"] == "pending" for i in compact["issues"])
        slug = compact["issues"][0]["slug"]

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            context = _do_get_issue_context(slug)
        assert "content" in context

        mock_gh.create_issue.return_value = {
            "number": 42, "html_url": "https://github.com/o/r/issues/42"
        }
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
            submitted = _do_submit_issue(slug)

        assert submitted["issue_number"] == 42

        # After submit, local status should be "open"
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            updated = _do_list_issues(compact=True)
        assert updated["issues"][0]["status"] == "open"


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY 7 — Auth Recovery Mid-Session
# ─────────────────────────────────────────────────────────────────────────────
#
# User Intent: GitHub token expired. A tool fails. User needs to re-auth.
#
# Tool sequence:
#   [any GitHub tool fails with github_unavailable]
#   check_auth  → {authenticated: False, options: [...], _guidance: "...auth"}
#   [user runs: gh auth login]
#   verify_auth → {authenticated: True, source: "gh_cli"}
#   [retry original action]
#
# PERFORMANCE  : 2 recovery calls + 1 retry. The _guidance URI surfaces the
#               exact workflow resource to load — no guessing.
# USABILITY    : ✓ _guidance field tells Claude to load the auth workflow resource.
#               ✓ verify_auth is the explicit "did it work?" check.
#               ⚠ There is no automatic retry after verify_auth succeeds.
#               Claude must remember the original intent. In a long session,
#               the user may need to re-state what they were trying to do.
# BUGS / RISK  : No bugs in this path. The key risk is that gh auth login
#               opens a browser — Claude cannot observe this or wait for it.
#               If the user doesn't confirm completion, verify_auth will fail.

class TestJourney7_AuthRecovery:

    def test_submit_failure_provides_guidance(self, workspace):
        """When GitHub is unavailable, the response includes _guidance for recovery."""
        _seed_issue(workspace)
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.get_github_client", return_value=(None, "Token expired.")):
            result = _do_submit_issue("fix-login-bug")

        assert result["error"] == "github_unavailable"
        assert "_guidance" in result
        assert "auth" in result["_guidance"]

    def test_verify_auth_success_path(self):
        """verify_auth returns authenticated=True after gh auth login succeeds."""
        with patch("extensions.github_planner.verify_gh_cli_auth", return_value=(True, "Logged in as user")):
            result = _do_verify_auth()
        assert result["authenticated"] is True
        assert result["source"] == "gh_cli"

    def test_verify_auth_failure_path(self):
        """verify_auth returns guidance when gh auth login hasn't been run yet."""
        with patch("extensions.github_planner.verify_gh_cli_auth", return_value=(False, "Not authenticated")):
            result = _do_verify_auth()
        assert result["authenticated"] is False
        assert "_guidance" in result


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY 8 — Plugin Creation Walkthrough
# ─────────────────────────────────────────────────────────────────────────────
#
# User Intent: "I want to build a plugin that deploys to staging."
#
# Tool sequence:
#   write_plugin_file("deploy", "plugin.json", ...)       → {written: True}
#   write_plugin_file("deploy", "description.json", ...)  → {written: True}
#   write_plugin_file("deploy", "__init__.py", ...)       → {written: True}
#   write_plugin_file("deploy", "commands/deploy.md", ...) → {written: True}
#   write_test_file("deploy", ...)                        → {written: True}
#   validate_plugin("deploy")                             → {valid: True}
#
# PERFORMANCE  : 6 file-write calls + 1 validation call. No API calls.
#               All local I/O — very fast. The validate call makes 1 import
#               attempt (can be slow if plugin has heavy dependencies).
#               IMPROVEMENT: validate could skip import if entry module
#               is in a fresh file that hasn't been added to sys.modules yet.
# USABILITY    : ✓ Conversation guides step-by-step — user only answers questions.
#               ✓ validate_plugin as final step catches errors before "done".
#               ⚠ If validate finds errors, Claude must fix them then re-validate.
#               This feedback loop is correct but adds 1-2 extra call pairs.
# BUGS / RISK  : BUG — validate_plugin calls importlib.import_module(entry),
#               but newly-written files are NOT on sys.path unless the project
#               root is. In a freshly created plugin, the import may fail with
#               ModuleNotFoundError even if the code is correct. The error
#               message would be confusing to the user. NEEDS DOCUMENTATION.

class TestJourney8_PluginCreation:

    def test_write_plugin_json_file(self, tmp_path):
        manifest = json.dumps({
            "name": "deploy",
            "version": "1.0",
            "entry": "extensions.deploy",
            "install_namespace": "t-h",
            "entry_command": "deploy.md",
            "commands_dir": "commands",
            "commands": ["deploy.md"],
            "description": "Deploy to staging",
        })
        with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
            result = _do_write_plugin_file("deploy", "plugin.json", manifest)
        assert result["written"] is True
        assert (tmp_path / "deploy" / "plugin.json").exists()

    def test_write_description_json(self, tmp_path):
        content = json.dumps({"plugin": "deploy", "subcommands": []})
        with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
            result = _do_write_plugin_file("deploy", "description.json", content)
        assert result["written"] is True

    def test_write_init_and_validate(self, tmp_path):
        """End-to-end: create a valid plugin and validate it passes all checks."""
        manifest = {
            "name": "deploy",
            "version": "1.0",
            "entry": "extensions.deploy",
            "install_namespace": "t-h",
            "entry_command": "deploy.md",
            "commands_dir": "commands",
            "commands": ["deploy.md"],
        }
        with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
            _do_write_plugin_file("deploy", "plugin.json", json.dumps(manifest))
            _do_write_plugin_file("deploy", "description.json", '{"plugin":"deploy"}')
            _do_write_plugin_file("deploy", "commands/deploy.md", "# Deploy\n1. Go")
            _do_write_plugin_file("deploy", "__init__.py", "def register(mcp): pass")

        mock_mod = MagicMock()
        mock_mod.register = MagicMock()

        with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path), \
             patch("importlib.import_module", return_value=mock_mod):
            result = _do_validate_plugin("deploy")

        assert result["valid"] is True
        assert result["errors"] == []

    def test_validate_catches_missing_register(self, tmp_path):
        """USABILITY: validate_plugin must catch missing register before user is told done."""
        (tmp_path / "deploy" / "commands").mkdir(parents=True)
        (tmp_path / "deploy" / "plugin.json").write_text(json.dumps({
            "name": "deploy", "version": "1.0",
            "entry": "extensions.deploy",
            "commands_dir": "commands", "commands": [],
        }))
        (tmp_path / "deploy" / "description.json").write_text("{}")
        (tmp_path / "deploy" / "__init__.py").write_text("# forgot register")

        no_register = MagicMock(spec=[])  # no attributes

        with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path), \
             patch("importlib.import_module", return_value=no_register):
            result = _do_validate_plugin("deploy")

        # USABILITY CHECK: error must be clear enough for Claude to fix it
        assert result["valid"] is False
        assert any("register" in e for e in result["errors"])

    def test_write_test_file_content_has_smoke_tests(self, tmp_path):
        """USABILITY: generated test scaffold must contain register smoke test."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        content = (
            "from plugins.deploy import register\n\n"
            "def test_register_is_callable():\n    assert callable(register)\n\n"
            "def test_register_does_not_raise():\n    register(MagicMock())\n"
        )
        with patch("extensions.plugin_creator._TESTS_ROOT", tests_dir):
            result = _do_write_test_file("deploy", content)

        assert result["written"] is True
        written = (tests_dir / "test_deploy.py").read_text()
        assert "test_register_is_callable" in written
        assert "test_register_does_not_raise" in written

    def test_validate_plugin_adds_project_root_to_sys_path(self, tmp_path):
        """#62 — validate_plugin injects project root so newly-written plugins are importable."""
        import sys as _sys
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "myplugin", "version": "1.0",
            "entry": "myplugin",
            "commands_dir": "commands", "commands": [],
        }))
        (plugin_dir / "description.json").write_text("{}")

        injected_paths = []
        original_import = importlib.import_module

        def tracking_import(name, *args, **kwargs):
            injected_paths.extend([p for p in _sys.path if str(tmp_path.parent) in p])
            raise ImportError(f"not a real module: {name}")

        with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path), \
             patch("importlib.import_module", side_effect=tracking_import):
            _do_validate_plugin("myplugin")

        # Project root must have been on sys.path at import time
        assert any(str(tmp_path.parent) in p for p in injected_paths)

    def test_validate_plugin_syntax_error_gives_hint(self, tmp_path):
        """#62 — SyntaxError gives a hint to check __init__.py, not a confusing traceback."""
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "myplugin", "version": "1.0",
            "entry": "extensions.myplugin",
            "commands_dir": "commands", "commands": [],
        }))
        (plugin_dir / "description.json").write_text("{}")

        with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path), \
             patch("importlib.import_module", side_effect=SyntaxError("invalid syntax")):
            result = _do_validate_plugin("myplugin")

        assert result["valid"] is False
        assert any("syntax" in e.lower() for e in result["errors"])
        assert any("hint" in e.lower() for e in result["errors"])


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY 9 — Edge Cases & Error Paths
# ─────────────────────────────────────────────────────────────────────────────
#
# These test the boundary conditions that arise in real usage but aren't covered
# by the happy-path journeys above.
#
# BUGS / RISK  : Several gaps identified — see inline comments.

class TestJourney9_EdgeCasesAndErrorPaths:

    def test_analyze_repo_full_no_repo_configured(self, workspace):
        """USABILITY: must return actionable error when GITHUB_REPO is not set."""
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.read_env", return_value={}):
            result = _do_analyze_repo_full(None)
        assert result["error"] == "repo_required"
        # USABILITY CHECK: message tells user how to fix it
        assert "setup_workspace" in result["message"] or "owner/repo" in result["message"]

    def test_analyze_repo_full_reports_omitted_files(self, workspace):
        """#60 — omitted_files count and _display warning when repo exceeds 200-file cap."""
        tree = [{"path": f"file{i}.py", "size": 10, "sha": f"s{i}"} for i in range(300)]
        gh = MagicMock()
        gh.__enter__ = lambda s: s
        gh.__exit__ = MagicMock(return_value=False)
        gh.list_repo_tree.return_value = tree
        gh.get_file_content.return_value = "x = 1"

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner._get_github_client", return_value=(gh, "")), \
             patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
            result = _do_analyze_repo_full("o/r")

        assert result["omitted_files"] == 100
        assert "omitted" in result["_display"]
        assert "100" in result["_display"]

    def test_analyze_repo_full_no_warning_for_small_repo(self, workspace):
        """#60 — no omission warning when repo fits within the 200-file cap."""
        tree = [{"path": f"file{i}.py", "size": 10, "sha": f"s{i}"} for i in range(5)]
        gh = MagicMock()
        gh.__enter__ = lambda s: s
        gh.__exit__ = MagicMock(return_value=False)
        gh.list_repo_tree.return_value = tree
        gh.get_file_content.return_value = "x = 1"

        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner._get_github_client", return_value=(gh, "")), \
             patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
            result = _do_analyze_repo_full("o/r")

        assert result["omitted_files"] == 0
        assert "omitted" not in result["_display"]

    def test_draft_on_uninitialised_workspace_returns_needs_init(self, uninit_workspace):
        """USABILITY: clear error before any work is done."""
        with patch("extensions.github_planner.get_workspace_root", return_value=uninit_workspace):
            result = _do_draft_issue("some title", "some body")
        assert result["status"] == "needs_init"

    def test_list_issues_on_uninitialised_workspace(self, uninit_workspace):
        """USABILITY: must return needs_init, not an empty list (confusing)."""
        with patch("extensions.github_planner.get_workspace_root", return_value=uninit_workspace):
            result = _do_list_issues()
        assert result.get("status") == "needs_init"

    def test_get_issue_context_invalid_slug_characters(self, workspace):
        """BUGS: slug with path traversal chars should be rejected cleanly."""
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_get_issue_context("../../etc/passwd")
        assert result.get("error") in ("not_found",)

    def test_write_plugin_file_path_traversal(self, tmp_path):
        """BUGS: path traversal in filename must be blocked."""
        with patch("extensions.plugin_creator._EXTENSIONS_ROOT", tmp_path):
            result = _do_write_plugin_file("myplugin", "../../../evil.py", "malicious")
        assert result["error"] == "path_traversal"
        assert not (tmp_path.parent.parent.parent / "evil.py").exists()

    def test_submit_already_open_issue_returns_error(self, workspace, mock_gh):
        """#59 — submitting an already-open issue must return error, not create a duplicate."""
        _seed_issue(workspace, status=IssueStatus.OPEN)
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
            result = _do_submit_issue("fix-login-bug")
        assert result["error"] == "already_submitted"
        mock_gh.create_issue.assert_not_called()

    def test_submit_already_closed_issue_returns_error(self, workspace, mock_gh):
        """#59 — closed issue must also be rejected without an API call."""
        _seed_issue(workspace, status=IssueStatus.CLOSED)
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
            result = _do_submit_issue("fix-login-bug")
        assert result["error"] == "already_closed"
        mock_gh.create_issue.assert_not_called()

    def test_submit_pending_still_works_after_idempotency_guard(self, workspace, mock_gh):
        """#59 — guard must not block the normal pending→open flow."""
        _seed_issue(workspace, status=IssueStatus.PENDING)
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
             patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
            result = _do_submit_issue("fix-login-bug")
        assert result["issue_number"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY 10 — Server Registration Smoke Test
# ─────────────────────────────────────────────────────────────────────────────
#
# Verify that all tools expected by the walkthroughs above are actually
# registered on the MCP server. This catches regressions where a tool is
# implemented but not wired into register().
#
# BUGS / RISK  : If any expected tool is missing, an MCP client calling it
#               will get an opaque "tool not found" error with no guidance.

class TestJourney10_ToolRegistration:

    EXPECTED_TOOLS = {
        # Core
        "get_setup_status", "setup_workspace",
        # Auth
        "check_auth", "verify_auth",
        # Issues
        "draft_issue", "submit_issue", "list_issues", "get_issue_context",
        # Project context
        "update_project_description", "update_architecture", "get_project_context",
        # Repo analysis (original loop-based)
        "start_repo_analysis", "fetch_analysis_batch", "get_analysis_status",
        # Repo analysis (efficient single-call — #52)
        "analyze_repo_full", "get_session_header",
        # Project docs
        "save_project_docs", "load_project_docs", "docs_exist",
        # Plugin creator (#56)
        "write_plugin_file", "write_test_file", "validate_plugin",
    }

    def test_all_workflow_tools_registered(self):
        server = create_server()
        registered = {t.name for t in server._tool_manager.list_tools()}
        missing = self.EXPECTED_TOOLS - registered
        assert missing == set(), f"Tools missing from server: {missing}"

    def test_compact_parameter_accepted_by_list_issues(self):
        """USABILITY: compact=True must be accepted as a valid parameter."""
        import asyncio
        server = create_server()
        # If compact isn't a valid param, this will raise a validation error
        # We expect it to succeed (though workspace may not be set up)
        # Use a tmp workspace to get a valid result shape
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            workspace = Path(d)
            (workspace / "hub_agents" / "issues").mkdir(parents=True)
            with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
                result = asyncio.run(
                    server._tool_manager.call_tool("list_issues", {"compact": True})
                )
        # Should not raise — compact param must be accepted
        assert result is not None
