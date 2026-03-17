"""Tests for repo analysis tools: start_repo_analysis, fetch_analysis_batch,
get_analysis_status, save_project_docs, load_project_docs, docs_exist."""
import asyncio
import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest

import plugins.github_planner as pg
from plugins.github_planner import (
    _ANALYSIS_CACHE,
    _PROJECT_DOCS_CACHE,
    _do_docs_exist,
    _do_draft_issue,
    _do_fetch_analysis_batch,
    _do_get_analysis_status,
    _do_load_project_docs,
    _do_save_project_docs,
    _do_start_repo_analysis,
    _gh_planner_docs_dir,
    _is_markdown,
)
from terminal_hub.server import create_server


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_tree(paths: list[str]) -> list[dict]:
    return [{"path": p, "size": 100} for p in paths]


def _mock_gh_with_tree(tree: list[dict]):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.list_repo_tree.return_value = tree
    return mock


def call(server, tool_name, args):
    return asyncio.run(server._tool_manager.call_tool(tool_name, args))


@pytest.fixture(autouse=True)
def clear_caches():
    """Ensure caches are clean before and after each test."""
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    yield
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


# ── _is_markdown ──────────────────────────────────────────────────────────────

def test_is_markdown_md():
    assert _is_markdown("README.md") is True


def test_is_markdown_rst():
    assert _is_markdown("docs/index.rst") is True


def test_is_markdown_py():
    assert _is_markdown("auth.py") is False


def test_is_markdown_case_insensitive():
    assert _is_markdown("NOTES.MD") is True


# ── start_repo_analysis ───────────────────────────────────────────────────────

def test_start_repo_analysis_partitions_md_first(workspace):
    tree = _make_tree(["src/auth.py", "README.md", "src/client.py", "TECH_STACK.md"])
    mock_gh = _mock_gh_with_tree(tree)
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_start_repo_analysis("o/r")

    assert result["status"] == "ready"
    assert result["md_count"] == 2
    assert result["code_count"] == 2
    state = _ANALYSIS_CACHE["o/r"]
    assert all(_is_markdown(f["path"]) for f in state["pending_md"])
    assert all(not _is_markdown(f["path"]) for f in state["pending_code"])


def test_start_repo_analysis_caps_at_200(workspace):
    tree = _make_tree([f"file{i}.py" for i in range(300)])
    mock_gh = _mock_gh_with_tree(tree)
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_start_repo_analysis("o/r")

    assert result["total_files"] == 200


def test_start_repo_analysis_no_auth_returns_error(workspace):
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner._get_github_client", return_value=(None, "No token.")), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_start_repo_analysis("o/r")

    assert result["error"] == "github_unavailable"


def test_start_repo_analysis_no_repo_returns_error(workspace):
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={}):
        result = _do_start_repo_analysis(None)

    assert result["error"] == "repo_required"


def test_start_repo_analysis_overwrites_existing_cache(workspace):
    _ANALYSIS_CACHE["o/r"] = {"pending_md": [], "pending_code": [{"path": "old.py", "size": 1}],
                               "analyzed": [], "skipped": [], "repo": "o/r",
                               "started_at": 0.0, "last_fetched": None}
    tree = _make_tree(["new.py"])
    mock_gh = _mock_gh_with_tree(tree)
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        _do_start_repo_analysis("o/r")

    assert _ANALYSIS_CACHE["o/r"]["pending_code"][0]["path"] == "new.py"


# ── fetch_analysis_batch ──────────────────────────────────────────────────────

def _seed_cache(repo: str, paths: list[str]) -> None:
    md = [{"path": p, "size": 10} for p in paths if _is_markdown(p)]
    code = [{"path": p, "size": 10} for p in paths if not _is_markdown(p)]
    _ANALYSIS_CACHE[repo] = {
        "pending_md": md, "pending_code": code,
        "analyzed": [], "skipped": [],
        "repo": repo, "started_at": time.time(), "last_fetched": None,
    }


def test_fetch_batch_returns_md_files_first(workspace):
    _seed_cache("o/r", ["README.md", "auth.py", "NOTES.md"])

    def _fake_content(path):
        return f"content of {path}"

    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.get_file_content.side_effect = _fake_content

    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_fetch_analysis_batch("o/r", batch_size=2)

    paths = [f["path"] for f in result["files"]]
    assert all(_is_markdown(p) for p in paths)
    assert result["analyzed_count"] == 2
    assert result["remaining_count"] == 1
    assert result["done"] is False


def test_fetch_batch_done_when_queues_empty(workspace):
    _seed_cache("o/r", ["README.md"])
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.get_file_content.return_value = "text"

    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_fetch_analysis_batch("o/r", batch_size=5)

    assert result["done"] is True
    assert result["remaining_count"] == 0


def test_fetch_batch_skips_binary_files(workspace):
    from plugins.github_planner.client import GitHubError
    _seed_cache("o/r", ["image.png"])
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.get_file_content.side_effect = GitHubError("binary", error_code="binary_file")

    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_fetch_analysis_batch("o/r", batch_size=5)

    assert result["files"] == []
    assert result["done"] is True
    assert _ANALYSIS_CACHE["o/r"]["skipped"][0]["reason"] == "binary_file"


def test_fetch_batch_not_started_returns_error(workspace):
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_fetch_analysis_batch("o/r")

    assert result["error"] == "analysis_not_started"


def test_fetch_batch_caps_batch_size_at_20(workspace):
    _seed_cache("o/r", [f"file{i}.py" for i in range(50)])
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.get_file_content.return_value = "x"

    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_fetch_analysis_batch("o/r", batch_size=99)

    assert len(result["files"]) == 20


# ── get_analysis_status ───────────────────────────────────────────────────────

def test_get_analysis_status_reflects_cache(workspace):
    _seed_cache("o/r", ["README.md", "auth.py"])
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_get_analysis_status("o/r")

    assert result["analyzed_count"] == 0
    assert result["remaining_count"] == 2
    assert result["done"] is False


def test_get_analysis_status_not_started(workspace):
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_get_analysis_status("o/r")

    assert result["error"] == "analysis_not_started"


# ── save_project_docs ─────────────────────────────────────────────────────────

def test_save_project_docs_writes_both_files(workspace):
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_save_project_docs("summary text", "detail text", "o/r")

    assert result["saved"] is True
    docs_dir = _gh_planner_docs_dir(workspace)
    assert (docs_dir / "project_summary.md").read_text() == "summary text"
    assert (docs_dir / "project_detail.md").read_text() == "detail text"


def test_save_project_docs_populates_cache(workspace):
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        _do_save_project_docs("sum", "det", "o/r")

    assert _PROJECT_DOCS_CACHE["o/r"]["summary"] == "sum"
    assert _PROJECT_DOCS_CACHE["o/r"]["detail"] == "det"


def test_save_project_docs_creates_parent_dirs(workspace):
    # docs_dir does not exist yet
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_save_project_docs("s", "d", "o/r")

    assert result["saved"] is True
    assert _gh_planner_docs_dir(workspace).exists()


# ── load_project_docs ─────────────────────────────────────────────────────────

def test_load_project_docs_returns_from_cache(workspace):
    _PROJECT_DOCS_CACHE["o/r"] = {"summary": "cached_sum", "detail": "cached_det", "loaded_at": time.time()}
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("summary", "o/r")

    assert result["summary"] == "cached_sum"


def test_load_project_docs_reads_disk_on_cache_miss(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("disk_sum")

    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("summary", "o/r")

    assert result["summary"] == "disk_sum"
    assert _PROJECT_DOCS_CACHE["o/r"]["summary"] == "disk_sum"


def test_load_project_docs_returns_none_when_missing(workspace):
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("summary", "o/r")

    assert result["summary"] is None


def test_load_project_docs_force_reload_bypasses_cache(workspace):
    _PROJECT_DOCS_CACHE["o/r"] = {"summary": "stale", "detail": None, "loaded_at": time.time()}
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("fresh")

    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("summary", "o/r", force_reload=True)

    assert result["summary"] == "fresh"


# ── docs_exist ────────────────────────────────────────────────────────────────

def test_docs_exist_returns_false_when_missing(workspace):
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace):
        result = _do_docs_exist()

    assert result["summary_exists"] is False
    assert result["detail_exists"] is False
    assert result["summary_age_hours"] is None


def test_docs_exist_returns_true_with_age(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("x")

    with patch("plugins.github_planner.get_workspace_root", return_value=workspace):
        result = _do_docs_exist()

    assert result["summary_exists"] is True
    assert isinstance(result["summary_age_hours"], float)
    assert result["summary_age_hours"] >= 0


# ── MCP tool registration ─────────────────────────────────────────────────────

def test_new_tools_registered(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
    tool_names = {t.name for t in server._tool_manager.list_tools()}
    for name in ("start_repo_analysis", "fetch_analysis_batch", "get_analysis_status",
                  "save_project_docs", "load_project_docs", "docs_exist"):
        assert name in tool_names, f"{name} not registered"


# ── #50 UX: _display format ───────────────────────────────────────────────────

def test_draft_issue_display_is_just_title(workspace):
    (workspace / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace):
        result = _do_draft_issue("My feature", "do it")
    assert result["_display"] == "✓ My feature"


def test_submit_issue_display_is_number_and_title(workspace):
    from plugins.github_planner import _do_submit_issue
    from plugins.github_planner.storage import write_issue_file, STATUS_PENDING
    from datetime import date
    write_issue_file(root=workspace, slug="my-feature", title="My feature", body="body",
                     assignees=[], labels=[], created_at=date(2026, 3, 17), status=STATUS_PENDING)
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.create_issue.return_value = {"number": 7, "html_url": "https://gh/7"}
    mock_gh.ensure_labels.return_value = None

    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_submit_issue("my-feature")

    assert result["_display"] == "✓ #7 My feature"


# ── Coverage gap-fillers ───────────────────────────────────────────────────────

def test_resolve_repo_uses_single_cache_entry(workspace):
    """Line 376: when exactly one repo is cached, _resolve_repo returns it."""
    _seed_cache("solo/repo", ["README.md"])
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={}):
        result = _do_get_analysis_status(None)
    # It found the solo entry and returned a proper status response (not repo_required)
    assert result.get("error") != "repo_required"
    assert result["repo"] == "solo/repo"


def test_start_repo_analysis_github_error_returns_error(workspace):
    """Lines 396-397: exception from list_repo_tree is caught."""
    from plugins.github_planner.client import GitHubError
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_repo_tree.side_effect = GitHubError("boom")
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_start_repo_analysis("o/r")
    assert result["error"] == "github_error"


def test_save_project_docs_returns_needs_init_when_not_set_up(tmp_path):
    """Line 498: ensure_initialized guard fires when hub_agents is missing."""
    with patch("plugins.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_save_project_docs("s", "d", "o/r")
    assert result["status"] == "needs_init"


def test_save_project_docs_write_error_returns_error(workspace):
    """Lines 509-510: OSError during write_text is caught."""
    from pathlib import Path
    original_write = Path.write_text

    def _fail_on_tmp(self, *args, **kwargs):
        if str(self).endswith(".tmp"):
            raise OSError("disk full")
        return original_write(self, *args, **kwargs)

    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}), \
         patch.object(Path, "write_text", _fail_on_tmp):
        result = _do_save_project_docs("s", "d", "o/r")
    assert result["error"] == "write_failed"


def test_load_project_docs_detail_from_cache(workspace):
    """Lines 534-536: cached detail path."""
    _PROJECT_DOCS_CACHE["o/r"] = {"summary": "s", "detail": "d", "loaded_at": time.time()}
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("detail", "o/r")
    assert result["detail"] == "d"
    assert result["summary"] is None


def test_load_project_docs_detail_from_disk(workspace):
    """Lines 552-554: disk detail path."""
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_detail.md").write_text("disk_detail")
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("detail", "o/r")
    assert result["detail"] == "disk_detail"
    assert result["summary"] is None


def test_load_project_docs_all_from_disk(workspace):
    """Line 554: doc='all' disk path."""
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("sum")
    (docs_dir / "project_detail.md").write_text("det")
    with patch("plugins.github_planner.get_workspace_root", return_value=workspace), \
         patch("plugins.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("all", "o/r")
    assert result["summary"] == "sum"
    assert result["detail"] == "det"
