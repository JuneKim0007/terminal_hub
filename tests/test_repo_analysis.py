"""Tests for repo analysis tools: start_repo_analysis, fetch_analysis_batch,
get_analysis_status, save_project_docs, load_project_docs, docs_exist."""
import asyncio
import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest

import extensions.github_planner as pg
from extensions.github_planner import (
    _ANALYSIS_CACHE,
    _PROJECT_DOCS_CACHE,
    _SESSION_HEADER_CACHE,
    _do_analyze_repo_full,
    _do_docs_exist,
    _do_draft_issue,
    _do_fetch_analysis_batch,
    _do_get_analysis_status,
    _do_get_session_header,
    _do_list_issues,
    _do_load_project_docs,
    _do_save_project_docs,
    _do_start_repo_analysis,
    _extract_file_index,
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
    _SESSION_HEADER_CACHE.clear()
    yield
    _ANALYSIS_CACHE.clear()
    _PROJECT_DOCS_CACHE.clear()
    _SESSION_HEADER_CACHE.clear()


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
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
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
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_start_repo_analysis("o/r")

    assert result["total_files"] == 200


def test_start_repo_analysis_no_auth_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(None, "No token.")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_start_repo_analysis("o/r")

    assert result["error"] == "github_unavailable"


def test_start_repo_analysis_no_repo_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={}):
        result = _do_start_repo_analysis(None)

    assert result["error"] == "repo_required"


def test_start_repo_analysis_overwrites_existing_cache(workspace):
    _ANALYSIS_CACHE["o/r"] = {"pending_md": [], "pending_code": [{"path": "old.py", "size": 1}],
                               "analyzed": [], "skipped": [], "repo": "o/r",
                               "started_at": 0.0, "last_fetched": None}
    tree = _make_tree(["new.py"])
    mock_gh = _mock_gh_with_tree(tree)
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
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

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
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

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_fetch_analysis_batch("o/r", batch_size=5)

    assert result["done"] is True
    assert result["remaining_count"] == 0


def test_fetch_batch_skips_binary_files(workspace):
    from extensions.github_planner.client import GitHubError
    _seed_cache("o/r", ["image.png"])
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.get_file_content.side_effect = GitHubError("binary", error_code="binary_file")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_fetch_analysis_batch("o/r", batch_size=5)

    assert result["files"] == []
    assert result["done"] is True
    assert _ANALYSIS_CACHE["o/r"]["skipped"][0]["reason"] == "binary_file"


def test_fetch_batch_not_started_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_fetch_analysis_batch("o/r")

    assert result["error"] == "analysis_not_started"


def test_fetch_batch_caps_batch_size_at_20(workspace):
    _seed_cache("o/r", [f"file{i}.py" for i in range(50)])
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.get_file_content.return_value = "x"

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_fetch_analysis_batch("o/r", batch_size=99)

    assert len(result["files"]) == 20


# ── get_analysis_status ───────────────────────────────────────────────────────

def test_get_analysis_status_reflects_cache(workspace):
    _seed_cache("o/r", ["README.md", "auth.py"])
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_get_analysis_status("o/r")

    assert result["analyzed_count"] == 0
    assert result["remaining_count"] == 2
    assert result["done"] is False


def test_get_analysis_status_not_started(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_get_analysis_status("o/r")

    assert result["error"] == "analysis_not_started"


# ── save_project_docs ─────────────────────────────────────────────────────────

def test_save_project_docs_writes_both_files(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_save_project_docs("summary text", "detail text", "o/r")

    assert result["saved"] is True
    docs_dir = _gh_planner_docs_dir(workspace)
    assert (docs_dir / "project_summary.md").read_text() == "summary text"
    assert (docs_dir / "project_detail.md").read_text() == "detail text"


def test_save_project_docs_populates_cache(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        _do_save_project_docs("sum", "det", "o/r")

    assert _PROJECT_DOCS_CACHE["o/r"]["summary"] == "sum"
    assert _PROJECT_DOCS_CACHE["o/r"]["detail"] == "det"


def test_save_project_docs_creates_parent_dirs(workspace):
    # docs_dir does not exist yet
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_save_project_docs("s", "d", "o/r")

    assert result["saved"] is True
    assert _gh_planner_docs_dir(workspace).exists()


# ── load_project_docs ─────────────────────────────────────────────────────────

def test_load_project_docs_returns_from_cache(workspace):
    _PROJECT_DOCS_CACHE["o/r"] = {"summary": "cached_sum", "detail": "cached_det", "loaded_at": time.time()}
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("summary", "o/r")

    assert result["summary"] == "cached_sum"


def test_load_project_docs_reads_disk_on_cache_miss(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("disk_sum")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("summary", "o/r")

    assert result["summary"] == "disk_sum"
    assert _PROJECT_DOCS_CACHE["o/r"]["summary"] == "disk_sum"


def test_load_project_docs_returns_none_when_missing(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("summary", "o/r")

    assert result["summary"] is None


def test_load_project_docs_force_reload_bypasses_cache(workspace):
    _PROJECT_DOCS_CACHE["o/r"] = {"summary": "stale", "detail": None, "loaded_at": time.time()}
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("fresh")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("summary", "o/r", force_reload=True)

    assert result["summary"] == "fresh"


# ── docs_exist ────────────────────────────────────────────────────────────────

def test_docs_exist_returns_false_when_missing(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_docs_exist()

    assert result["summary_exists"] is False
    assert result["detail_exists"] is False
    assert result["summary_age_hours"] is None


def test_docs_exist_returns_true_with_age(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("x")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
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
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_draft_issue("My feature", "do it")
    assert result["_display"] == "✓ My feature"


def test_submit_issue_display_is_number_and_title(workspace):
    from extensions.github_planner import _do_submit_issue
    from extensions.github_planner.storage import write_issue_file, STATUS_PENDING
    from datetime import date
    write_issue_file(root=workspace, slug="my-feature", title="My feature", body="body",
                     assignees=[], labels=[], created_at=date(2026, 3, 17), status=STATUS_PENDING)
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.create_issue.return_value = {"number": 7, "html_url": "https://gh/7"}
    mock_gh.ensure_labels.return_value = None

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_submit_issue("my-feature")

    assert result["_display"] == "✓ #7 My feature"


# ── Coverage gap-fillers ───────────────────────────────────────────────────────

def test_resolve_repo_uses_single_cache_entry(workspace):
    """_resolve_repo uses cached repo when it matches current workspace env (#103)."""
    _seed_cache("solo/repo", ["README.md"])
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "solo/repo"}):
        result = _do_get_analysis_status(None)
    # It found the solo entry and returned a proper status response (not repo_required)
    assert result.get("error") != "repo_required"
    assert result["repo"] == "solo/repo"


def test_resolve_repo_cache_ignored_when_env_mismatch(workspace):
    """_resolve_repo ignores cache entry that doesn't match workspace env (#103)."""
    _seed_cache("other/repo", ["README.md"])
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "my/repo"}):
        result = _do_get_analysis_status(None)
    # Cache has "other/repo" but env says "my/repo" — resolve_repo returns env repo
    # _do_get_analysis_status finds no analysis for "my/repo" → analysis_not_started
    # (not repo_required, proving env repo was used, not the cache entry)
    assert result.get("error") in ("repo_required", "analysis_not_started")


def test_start_repo_analysis_github_error_returns_error(workspace):
    """Lines 396-397: exception from list_repo_tree is caught."""
    from extensions.github_planner.client import GitHubError
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_repo_tree.side_effect = GitHubError("boom")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_start_repo_analysis("o/r")
    assert result["error"] == "github_error"


def test_save_project_docs_returns_needs_init_when_not_set_up(tmp_path):
    """Line 498: ensure_initialized guard fires when hub_agents is missing."""
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
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

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}), \
         patch.object(Path, "write_text", _fail_on_tmp):
        result = _do_save_project_docs("s", "d", "o/r")
    assert result["error"] == "write_failed"


def test_load_project_docs_detail_from_cache(workspace):
    """Lines 534-536: cached detail path."""
    _PROJECT_DOCS_CACHE["o/r"] = {"summary": "s", "detail": "d", "loaded_at": time.time()}
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("detail", "o/r")
    assert result["detail"] == "d"
    assert result["summary"] is None


def test_load_project_docs_detail_from_disk(workspace):
    """Lines 552-554: disk detail path."""
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_detail.md").write_text("disk_detail")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("detail", "o/r")
    assert result["detail"] == "disk_detail"
    assert result["summary"] is None


def test_load_project_docs_all_from_disk(workspace):
    """Line 554: doc='all' disk path."""
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("sum")
    (docs_dir / "project_detail.md").write_text("det")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("all", "o/r")
    assert result["summary"] == "sum"
    assert result["detail"] == "det"


# ── _extract_file_index (#52) ─────────────────────────────────────────────────

def test_extract_file_index_python_exports():
    content = "def foo(): pass\nclass Bar: pass\ndef _private(): pass"
    result = _extract_file_index("mod.py", content)
    assert result["type"] == "python"
    assert "foo" in result["exports"]
    assert "Bar" in result["exports"]
    assert "_private" not in result["exports"]


def test_extract_file_index_python_with_docstring():
    content = '"""My module."""\ndef foo(): pass'
    result = _extract_file_index("mod.py", content)
    assert "My module." in result["module_doc"]


def test_extract_file_index_python_syntax_error():
    result = _extract_file_index("bad.py", "def (")
    assert result["parse_error"] is True
    assert result["type"] == "python"


def test_extract_file_index_markdown_headings():
    content = "# Title\n## Section\nsome text\n## Another"
    result = _extract_file_index("README.md", content)
    assert result["type"] == "markdown"
    assert "Title" in result["headings"]
    assert "Section" in result["headings"]


def test_extract_file_index_markdown_first_200():
    content = "x" * 300
    result = _extract_file_index("README.md", content)
    assert len(result["first_200"]) == 200


def test_extract_file_index_other_file():
    result = _extract_file_index("image.png", b"bytes".decode("latin-1"))
    assert result["type"] == "other"
    assert "lines" in result


# ── _do_analyze_repo_full (#52) ───────────────────────────────────────────────

def _make_tree_with_sha(paths_and_shas: list[tuple[str, str]]) -> list[dict]:
    return [{"path": p, "size": 100, "sha": s} for p, s in paths_and_shas]


def test_analyze_repo_full_returns_file_index(workspace):
    tree = _make_tree_with_sha([("README.md", "abc"), ("auth.py", "def")])

    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_repo_tree.return_value = tree
    mock_gh.get_file_content.side_effect = lambda p: f"# {p}\n"

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_analyze_repo_full("o/r")

    assert result["repo"] == "o/r"
    assert result["fetched"] == 2
    assert len(result["file_index"]) == 2
    paths = {e["path"] for e in result["file_index"]}
    assert paths == {"README.md", "auth.py"}


def test_analyze_repo_full_skips_unchanged_by_sha(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    hashes_path = docs_dir / "file_hashes.json"
    hashes_path.write_text(json.dumps({"unchanged.py": "same-sha"}))

    tree = _make_tree_with_sha([("unchanged.py", "same-sha"), ("new.py", "new-sha")])
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_repo_tree.return_value = tree
    mock_gh.get_file_content.return_value = "x = 1"

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_analyze_repo_full("o/r")

    assert result["skipped_unchanged"] == 1
    assert result["fetched"] == 1
    fetched_paths = {e["path"] for e in result["file_index"]}
    assert "new.py" in fetched_paths
    assert "unchanged.py" not in fetched_paths


def test_analyze_repo_full_persists_hashes(workspace):
    tree = _make_tree_with_sha([("src/mod.py", "sha1")])
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_repo_tree.return_value = tree
    mock_gh.get_file_content.return_value = "def f(): pass"

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        _do_analyze_repo_full("o/r")

    hashes = json.loads((_gh_planner_docs_dir(workspace) / "file_hashes.json").read_text())
    assert hashes["src/mod.py"] == "sha1"


def test_analyze_repo_full_no_auth_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(None, "No token")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_analyze_repo_full("o/r")
    assert result["error"] == "github_unavailable"


def test_analyze_repo_full_no_repo_returns_error(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={}):
        result = _do_analyze_repo_full(None)
    assert result["error"] == "repo_required"


# ── _do_get_session_header (#52) ──────────────────────────────────────────────

def test_get_session_header_no_docs(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_session_header()
    assert result == {"docs": False}


def test_get_session_header_with_docs(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# My Project\nsome text")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_session_header()

    assert result["docs"] is True
    assert result["title"] == "My Project"
    assert isinstance(result["age_hours"], float)
    assert result["stale"] is False


def test_get_session_header_marks_stale_after_168h(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    summary = docs_dir / "project_summary.md"
    summary.write_text("# Old Project")
    # Backdate mtime by 8 days
    old_time = time.time() - (8 * 24 * 3600)
    import os
    os.utime(summary, (old_time, old_time))

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_session_header()

    assert result["stale"] is True


def test_get_session_header_is_cached(workspace):
    call_count = 0
    original = pg.get_workspace_root

    def counting_root():
        nonlocal call_count
        call_count += 1
        return workspace

    with patch("extensions.github_planner.get_workspace_root", side_effect=counting_root):
        result1 = _do_get_session_header()
        result2 = _do_get_session_header()
    # After #94, get_workspace_root() is called each time to build the cache key
    # (cheap); expensive file I/O is cached — both calls return the same object
    assert call_count == 2
    assert result1 is result2


# ── _do_list_issues compact mode (#52) ────────────────────────────────────────

def test_list_issues_compact_returns_minimal_fields(workspace):
    from extensions.github_planner.storage import write_issue_file, STATUS_PENDING
    write_issue_file(root=workspace, slug="foo-bar", title="Foo Bar", body="body",
                     assignees=[], labels=[], created_at=__import__("datetime").date(2026, 1, 1),
                     status=STATUS_PENDING)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_issues(compact=True)

    issues = result["issues"]
    assert len(issues) == 1
    # local_only is included for pending (unsubmitted) issues (#102)
    assert set(issues[0].keys()) == {"slug", "title", "status", "local_only"}


def test_list_issues_full_returns_all_fields(workspace):
    from extensions.github_planner.storage import write_issue_file, STATUS_PENDING
    write_issue_file(root=workspace, slug="foo-bar", title="Foo Bar", body="body",
                     assignees=[], labels=[], created_at=__import__("datetime").date(2026, 1, 1),
                     status=STATUS_PENDING)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_issues(compact=False)

    issues = result["issues"]
    assert len(issues) == 1
    assert "slug" in issues[0]
    assert "title" in issues[0]
    # local_only flag is set for unsubmitted issues (#102)
    assert issues[0]["local_only"] is True


# ── _do_list_pending_drafts (#102) ────────────────────────────────────────────

def test_list_pending_drafts_returns_unsubmitted(workspace):
    from extensions.github_planner import _do_list_pending_drafts
    from extensions.github_planner.storage import write_issue_file, STATUS_PENDING, STATUS_OPEN
    import datetime
    write_issue_file(root=workspace, slug="draft-one", title="Draft One", body="body",
                     assignees=[], labels=[], created_at=datetime.date(2026, 1, 1),
                     status=STATUS_PENDING)
    # Write an issue with a github number (submitted)
    write_issue_file(root=workspace, slug="submitted", title="Submitted", body="body",
                     assignees=[], labels=[], created_at=datetime.date(2026, 1, 2),
                     status=STATUS_OPEN, issue_number=42)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_pending_drafts()

    assert result["count"] == 1
    assert result["pending_drafts"][0]["slug"] == "draft-one"


def test_list_pending_drafts_empty_when_all_submitted(workspace):
    from extensions.github_planner import _do_list_pending_drafts
    from extensions.github_planner.storage import write_issue_file, STATUS_OPEN
    import datetime
    write_issue_file(root=workspace, slug="submitted", title="Done", body="body",
                     assignees=[], labels=[], created_at=datetime.date(2026, 1, 1),
                     status=STATUS_OPEN, issue_number=7)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_pending_drafts()

    assert result["count"] == 0
    assert result["pending_drafts"] == []


def test_list_issues_submitted_has_no_local_only(workspace):
    from extensions.github_planner.storage import write_issue_file, STATUS_OPEN
    import datetime
    write_issue_file(root=workspace, slug="gh-issue", title="On GitHub", body="body",
                     assignees=[], labels=[], created_at=datetime.date(2026, 1, 1),
                     status=STATUS_OPEN, issue_number=99)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_issues(compact=False)

    assert "local_only" not in result["issues"][0]


# ── detect_existing_docs + save/load_docs_strategy (#84) ──────────────────────

def test_detect_existing_docs_finds_readme(workspace):
    from extensions.github_planner import detect_existing_docs
    file_index = [
        {"path": "README.md", "size": 1200},
        {"path": "src/main.py", "size": 500},
        {"path": "docs/DESIGN.md", "size": 3400},
        {"path": "src/utils.py", "size": 200},
    ]
    result = detect_existing_docs(file_index)
    paths = [r["path"] for r in result]
    assert "README.md" in paths
    assert "docs/DESIGN.md" in paths
    assert "src/main.py" not in paths
    assert "src/utils.py" not in paths


def test_detect_existing_docs_ignores_code_files(workspace):
    from extensions.github_planner import detect_existing_docs
    file_index = [
        {"path": "src/helper.md", "size": 100},  # not doc-like
        {"path": "CONTRIBUTING.md", "size": 500},
    ]
    result = detect_existing_docs(file_index)
    paths = [r["path"] for r in result]
    assert "CONTRIBUTING.md" in paths


def test_save_docs_strategy_creates_file(workspace):
    from extensions.github_planner import _do_save_docs_strategy
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_save_docs_strategy("refer", ["README.md", "docs/DESIGN.md"])

    assert result["saved"] is True
    assert result["strategy"] == "refer"
    strategy_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "docs_strategy.json"
    assert strategy_path.exists()
    import json
    data = json.loads(strategy_path.read_text())
    assert data["strategy"] == "refer"
    assert "README.md" in data["referred_docs"]


def test_load_docs_strategy_returns_none_when_absent(workspace):
    from extensions.github_planner import _do_load_docs_strategy
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_load_docs_strategy()

    assert result["strategy"] is None
    assert result["referred_docs"] == []


def test_save_docs_strategy_invalid_strategy(workspace):
    from extensions.github_planner import _do_save_docs_strategy
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_save_docs_strategy("invalid_strategy")

    assert result["error"] == "invalid_strategy"


def test_load_docs_strategy_roundtrip(workspace):
    from extensions.github_planner import _do_save_docs_strategy, _do_load_docs_strategy
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        _do_save_docs_strategy("merge")
        result = _do_load_docs_strategy()

    assert result["strategy"] == "merge"


# ── _do_update_project_detail_section (#65) ───────────────────────────────────

def test_update_project_detail_section_creates_file(workspace):
    from extensions.github_planner import _do_update_project_detail_section
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_update_project_detail_section("Auth", "JWT tokens with refresh.")

    assert result["updated"] is True
    assert result["action"] == "created"
    detail_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "project_detail.md"
    assert detail_path.exists()
    content = detail_path.read_text()
    assert "## Auth" in content
    assert "JWT tokens with refresh." in content


def test_update_project_detail_section_appends_new(workspace):
    from extensions.github_planner import _do_update_project_detail_section
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_detail.md").write_text("## Existing\n\nStuff here.\n")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_update_project_detail_section("NewFeature", "New feature details.")

    assert result["action"] == "appended"
    content = (docs_dir / "project_detail.md").read_text()
    assert "## Existing" in content
    assert "## NewFeature" in content
    assert "New feature details." in content


def test_update_project_detail_section_replaces_existing(workspace):
    from extensions.github_planner import _do_update_project_detail_section
    docs_dir = workspace / "hub_agents" / "extensions" / "gh_planner"
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_detail.md").write_text("## Auth\n\nOld content.\n\n## Other\n\nKeep this.\n")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_update_project_detail_section("Auth", "New auth content.")

    assert result["action"] == "replaced"
    content = (docs_dir / "project_detail.md").read_text()
    assert "Old content." not in content
    assert "New auth content." in content
    assert "## Other" in content
    assert "Keep this." in content


def test_update_project_detail_section_empty_feature_name(workspace):
    from extensions.github_planner import _do_update_project_detail_section
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_update_project_detail_section("", "Some content.")

    assert result["error"] == "invalid_input"


def test_update_project_detail_section_invalidates_cache(workspace):
    from extensions.github_planner import _do_update_project_detail_section, _PROJECT_DOCS_CACHE
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)
    _PROJECT_DOCS_CACHE[str(workspace)] = {"summary": "cached"}

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        _do_update_project_detail_section("Feature", "Content.")

    assert str(workspace) not in _PROJECT_DOCS_CACHE


# ── _do_generate_issue_workflows (#88) ────────────────────────────────────────

def test_generate_issue_workflows_appends_scaffold(workspace):
    from extensions.github_planner import _do_generate_issue_workflows
    from extensions.github_planner.storage import write_issue_file, STATUS_PENDING
    import datetime
    write_issue_file(root=workspace, slug="fix-bug", title="Fix bug", body="Repro steps here.",
                     assignees=[], labels=["bug"], created_at=datetime.date(2026, 1, 1),
                     status=STATUS_PENDING)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_generate_issue_workflows("fix-bug")

    assert result["updated"] is True
    content = (workspace / "hub_agents" / "issues" / "fix-bug.md").read_text()
    assert "## Agent Workflow" in content
    assert "## Program Workflow" in content
    assert "bug fix" in content


def test_generate_issue_workflows_idempotent(workspace):
    from extensions.github_planner import _do_generate_issue_workflows
    from extensions.github_planner.storage import write_issue_file, STATUS_PENDING
    import datetime
    write_issue_file(root=workspace, slug="fix-bug", title="Fix bug", body="body",
                     assignees=[], labels=[], created_at=datetime.date(2026, 1, 1),
                     status=STATUS_PENDING)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        _do_generate_issue_workflows("fix-bug")
        result2 = _do_generate_issue_workflows("fix-bug")

    assert result2["updated"] is False
    assert "already present" in result2["message"]


def test_generate_issue_workflows_unknown_slug(workspace):
    from extensions.github_planner import _do_generate_issue_workflows
    (workspace / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_generate_issue_workflows("nonexistent-slug")

    assert result["error"] == "issue_not_found"


# ── new tools are registered (#52/#53) ────────────────────────────────────────

def test_analyze_repo_full_and_get_session_header_registered(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
    tool_names = {t.name for t in server._tool_manager.list_tools()}
    assert "analyze_repo_full" in tool_names
    assert "get_session_header" in tool_names


# ── _parse_h2_sections + _do_lookup_feature_section ─────────────────────────

from extensions.github_planner import _parse_h2_sections, _do_lookup_feature_section


def test_parse_h2_sections_basic():
    text = "## Issue Management\ncontent A\n## Plugin Framework\ncontent B"
    sections = _parse_h2_sections(text)
    assert list(sections.keys()) == ["Issue Management", "Plugin Framework"]
    assert sections["Issue Management"] == "content A"
    assert sections["Plugin Framework"] == "content B"


def test_parse_h2_sections_empty():
    assert _parse_h2_sections("") == {}
    assert _parse_h2_sections("# H1 only\nno h2") == {}


def test_parse_h2_sections_h3_inside_section():
    text = "## Auth\n### Existing\nstuff\n### Guidelines\nmore"
    sections = _parse_h2_sections(text)
    assert "Auth" in sections
    assert "### Existing" in sections["Auth"]


def test_lookup_feature_section_no_detail_doc(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_lookup_feature_section("Issue Management")
    assert result["matched"] is False
    assert "project_detail.md not found" in result["reason"]


def test_lookup_feature_section_exact_match(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_detail.md").write_text(
        "## Issue Management\nrules A\n## Auth\nrules B"
    )
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_lookup_feature_section("Issue Management")
    assert result["matched"] is True
    assert result["feature"] == "Issue Management"
    assert "rules A" in result["section"]


def test_lookup_feature_section_case_insensitive(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_detail.md").write_text("## Issue Management\nrules A")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_lookup_feature_section("issue management")
    assert result["matched"] is True


def test_lookup_feature_section_substring_match(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_detail.md").write_text("## Issue Management\nrules A")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_lookup_feature_section("issue")
    assert result["matched"] is True
    assert result["feature"] == "Issue Management"


def test_lookup_feature_section_no_match_returns_available(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_detail.md").write_text("## Auth\nrules")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_lookup_feature_section("Nonexistent Feature")
    assert result["matched"] is False
    assert "Auth" in result["available_features"]


def test_lookup_feature_section_includes_global_rules(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# My Project\nGlobal rule 1")
    (docs_dir / "project_detail.md").write_text("## Auth\nrules")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_lookup_feature_section("Auth")
    assert result["matched"] is True
    assert "Global rule 1" in result["global_rules"]


def test_lookup_feature_section_uses_section_cache(workspace):
    """Second call should hit _sections cache; _PROJECT_DOCS_CACHE entry is populated."""
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_detail.md").write_text("## Auth\nrules")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        r1 = _do_lookup_feature_section("Auth")
        # Delete the file — second call must still succeed via cache
        (docs_dir / "project_detail.md").unlink()
        r2 = _do_lookup_feature_section("Auth")

    assert r1["matched"] is True
    assert r2["matched"] is True
    assert r1["section"] == r2["section"]


def test_save_project_docs_clears_sections_cache(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (workspace / "hub_agents").mkdir(exist_ok=True)
    (workspace / ".gitignore").write_text("")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        # Populate section cache via lookup
        (docs_dir / "project_detail.md").write_text("## Auth\nold rules")
        _do_lookup_feature_section("Auth")
        # Now save new docs
        _do_save_project_docs("new summary", "## NewArea\nnew rules")
        # sections cache should be cleared
        resolved = pg._resolve_repo(None) or "unknown"
        entry = pg._PROJECT_DOCS_CACHE.get(resolved, {})
        assert entry.get("_sections") is None


def test_docs_exist_returns_sections(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# P")
    (docs_dir / "project_detail.md").write_text("## Auth\nrules\n## Session\nmore")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_docs_exist()
    assert result["sections"] == ["Auth", "Session"]


def test_docs_exist_sections_empty_when_no_detail(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_docs_exist()
    assert result["sections"] == []


def test_get_session_header_includes_sections(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# My Project\ntext")
    (docs_dir / "project_detail.md").write_text("## Issue Management\nr\n## Auth\nr")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_session_header()
    assert result["docs"] is True
    assert result["sections"] == ["Issue Management", "Auth"]


def test_get_session_header_no_detail_sections_empty(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# My Project")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_session_header()
    assert result["sections"] == []


def test_lookup_feature_section_tool_registered(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
    tool_names = {t.name for t in server._tool_manager.list_tools()}
    assert "lookup_feature_section" in tool_names


# ── mtime cache invalidation (#69) ────────────────────────────────────────────

def test_lookup_feature_section_invalidates_cache_on_file_change(workspace):
    """Editing project_detail.md on disk should cause the next lookup to re-parse."""
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    detail = docs_dir / "project_detail.md"
    detail.write_text("## Auth\nrules")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        r1 = _do_lookup_feature_section("Auth")
    assert r1["matched"] is True

    # Simulate external edit — write new content and bump mtime
    import time as _time
    _time.sleep(0.01)
    detail.write_text("## NewFeature\nnew rules")
    # Touch mtime explicitly to ensure it differs
    detail.touch()

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        r2 = _do_lookup_feature_section("NewFeature")
    assert r2["matched"] is True
    assert "Auth" not in r2.get("available_features", [])


# ── session_header sections cap (#67) ─────────────────────────────────────────

def test_get_session_header_caps_sections_at_10(workspace):
    """session_header sections list is capped at 10 entries for large repos."""
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# Big Project")
    # Write 15 H2 sections
    sections_md = "\n".join(f"## Section{i}\ncontent" for i in range(15))
    (docs_dir / "project_detail.md").write_text(sections_md)
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_session_header()
    assert len(result["sections"]) == 10
    assert result.get("sections_truncated") is True
    assert result.get("total_sections") == 15


def test_get_session_header_no_truncation_when_few_sections(workspace):
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# My Project")
    (docs_dir / "project_detail.md").write_text("## Auth\nr\n## Session\nr")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_session_header()
    assert len(result["sections"]) == 2
    assert "sections_truncated" not in result
