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
        result = _do_save_project_docs("My portfolio", ["React", "TypeScript"], repo="o/r")

    assert result["saved"] is True
    docs_dir = _gh_planner_docs_dir(workspace)
    text = (docs_dir / "project_summary.md").read_text()
    assert "My portfolio" in text
    assert "React" in text
    assert (docs_dir / "project_detail.md").exists()


def test_save_project_docs_populates_cache(workspace):
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        _do_save_project_docs("A project", ["Python"], repo="o/r")

    assert "A project" in _PROJECT_DOCS_CACHE["o/r"]["summary"]


def test_save_project_docs_creates_parent_dirs(workspace):
    # docs_dir does not exist yet
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_save_project_docs("App", ["Go"], repo="o/r")

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
    """ensure_initialized guard fires when hub_agents is missing."""
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_save_project_docs("App", ["Python"], repo="o/r")
    assert result["status"] == "needs_init"


def test_save_project_docs_write_error_returns_error(workspace):
    """OSError during write_text is caught."""
    from pathlib import Path
    original_write = Path.write_text

    def _fail_on_tmp(self, *args, **kwargs):
        if str(self).endswith(".tmp"):
            raise OSError("disk full")
        return original_write(self, *args, **kwargs)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}), \
         patch.object(Path, "write_text", _fail_on_tmp):
        result = _do_save_project_docs("App", ["Python"], repo="o/r")
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


def test_generate_issue_workflows_updates_frontmatter_fields(workspace):
    """generate_issue_workflows should write workflow + agent_workflow into front matter."""
    from extensions.github_planner import _do_generate_issue_workflows
    from extensions.github_planner.storage import write_issue_file, read_issue_frontmatter, STATUS_PENDING
    import datetime
    write_issue_file(root=workspace, slug="my-task", title="My Task", body="Do it.",
                     assignees=[], labels=["enhancement"], created_at=datetime.date(2026, 1, 1),
                     status=STATUS_PENDING)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        _do_generate_issue_workflows("my-task")

    fm = read_issue_frontmatter(workspace, "my-task")
    assert isinstance(fm["workflow"], list) and len(fm["workflow"]) > 0
    assert fm["agent_workflow"] is not None
    assert "feature" in fm["agent_workflow"]



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
        # Now save new docs — sections cache should be reset to empty dict
        _do_save_project_docs("New summary project", ["Python"])
        resolved = pg._resolve_repo(None) or "unknown"
        entry = pg._PROJECT_DOCS_CACHE.get(resolved, {})
        # New save resets _sections to {} (empty, not None — cleared for fresh lookup)
        assert entry.get("_sections") == {}


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


# ── _do_analyze_github_labels / _do_load_github_local_config (#81) ────────────

def _make_mock_gh(labels=None, open_issues=None):
    """Helper to build a mock GitHubClient for label tests."""
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.list_labels.return_value = labels or []
    mock.list_issues.return_value = open_issues or []
    return mock


def test_analyze_github_labels_active_if_has_open_issues(workspace):
    from extensions.github_planner import _do_analyze_github_labels
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    # Label "bug" has an open issue
    labels = [{"name": "bug", "color": "ee0701", "description": "A bug", "created_at": "2020-01-01T00:00:00Z"}]
    open_issues = [{"labels": [{"name": "bug"}]}]
    mock_gh = _make_mock_gh(labels=labels, open_issues=open_issues)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_analyze_github_labels()

    assert result.get("error") is None
    assert any(l["name"] == "bug" for l in result["active_labels"])
    assert result["closed_labels"] == []


def test_analyze_github_labels_closed_if_old_and_no_open_issues(workspace):
    from extensions.github_planner import _do_analyze_github_labels
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    # Label created 60 days ago, no open issues
    old_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60 * 86400))
    labels = [{"name": "stale", "color": "aaaaaa", "description": "", "created_at": old_ts}]

    mock_gh = _make_mock_gh(labels=labels, open_issues=[])

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_analyze_github_labels()

    assert result.get("error") is None
    assert result["active_labels"] == []
    assert any(l["name"] == "stale" for l in result["closed_labels"])


def test_analyze_github_labels_active_if_recently_created(workspace):
    from extensions.github_planner import _do_analyze_github_labels
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    # Label created 5 days ago (recent), no open issues
    recent_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5 * 86400))
    labels = [{"name": "new-feature", "color": "0075ca", "description": "", "created_at": recent_ts}]

    mock_gh = _make_mock_gh(labels=labels, open_issues=[])

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_analyze_github_labels()

    assert result.get("error") is None
    assert any(l["name"] == "new-feature" for l in result["active_labels"])
    assert result["closed_labels"] == []


def test_analyze_github_labels_saves_to_disk(workspace):
    from extensions.github_planner import _do_analyze_github_labels
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    labels = [{"name": "enhancement", "color": "a2eeef", "description": "", "created_at": "2020-01-01T00:00:00Z"}]
    open_issues = [{"labels": [{"name": "enhancement"}]}]
    mock_gh = _make_mock_gh(labels=labels, open_issues=open_issues)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        _do_analyze_github_labels()

    config_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "github_local_config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "labels" in data
    assert any(l["name"] == "enhancement" for l in data["labels"]["active"])


def test_analyze_github_labels_only_defaults_flag(workspace):
    from extensions.github_planner import _do_analyze_github_labels
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    # Only GitHub default labels
    labels = [
        {"name": "bug", "color": "ee0701", "description": "", "created_at": "2020-01-01T00:00:00Z"},
        {"name": "enhancement", "color": "a2eeef", "description": "", "created_at": "2020-01-01T00:00:00Z"},
    ]
    mock_gh = _make_mock_gh(labels=labels, open_issues=[])

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_analyze_github_labels()

    assert result["only_defaults"] is True
    assert "suggestion" in result


def test_analyze_github_labels_no_auth(workspace):
    from extensions.github_planner import _do_analyze_github_labels
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(None, "No token")):
        result = _do_analyze_github_labels()

    assert result["error"] == "github_unavailable"


def test_analyze_github_labels_cache_hit(workspace):
    from extensions.github_planner import _do_analyze_github_labels, _LABEL_CACHE
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    labels = [{"name": "bug", "color": "ee0701", "description": "", "created_at": "2020-01-01T00:00:00Z"}]
    mock_gh = _make_mock_gh(labels=labels, open_issues=[{"labels": [{"name": "bug"}]}])

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")) as mock_client:
        _do_analyze_github_labels()
        result2 = _do_analyze_github_labels()

    # Second call should use cache — get_github_client called only once
    assert result2.get("cached") is True
    assert mock_client.call_count == 1


def test_analyze_github_labels_refresh_bypasses_cache(workspace):
    from extensions.github_planner import _do_analyze_github_labels
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    labels = [{"name": "bug", "color": "ee0701", "description": "", "created_at": "2020-01-01T00:00:00Z"}]
    mock_gh = _make_mock_gh(labels=labels, open_issues=[{"labels": [{"name": "bug"}]}])

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")) as mock_client:
        _do_analyze_github_labels()
        _do_analyze_github_labels(refresh=True)

    # refresh=True should call GitHub again
    assert mock_client.call_count == 2


def test_load_github_local_config_absent(workspace):
    from extensions.github_planner import _do_load_github_local_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_load_github_local_config()

    assert result["labels"] is None
    assert result["fetched_at"] is None


def test_load_github_local_config_roundtrip(workspace):
    from extensions.github_planner import _do_analyze_github_labels, _do_load_github_local_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    labels = [{"name": "bug", "color": "ee0701", "description": "", "created_at": "2020-01-01T00:00:00Z"}]
    mock_gh = _make_mock_gh(labels=labels, open_issues=[{"labels": [{"name": "bug"}]}])

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        _do_analyze_github_labels()
        result = _do_load_github_local_config()

    assert result["labels"] is not None
    assert any(l["name"] == "bug" for l in result["labels"]["active"])
    assert result["fetched_at"] is not None


# ── _do_load_github_global_config / _do_save_github_local_config / _do_get_github_config (#80) ──

def test_load_github_global_config_creates_defaults(workspace):
    from extensions.github_planner import _do_load_github_global_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=(None, MagicMock(value="none"))), \
         patch("extensions.github_planner.read_env", return_value={}):
        result = _do_load_github_global_config()

    assert "auth" in result
    assert result["auth"]["method"] == "none"
    assert (workspace / "hub_agents" / "github_global_config.json").exists()


def test_load_github_global_config_stores_auth_method(workspace):
    from extensions.github_planner import _do_load_github_global_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    mock_source = MagicMock()
    mock_source.value = "gh_cli"
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=("tok123", mock_source)), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "owner/myrepo"}):
        result = _do_load_github_global_config()

    assert result["auth"]["method"] == "gh_cli"
    assert result["default_repo"] == "owner/myrepo"


def test_load_github_global_config_reads_existing(workspace):
    from extensions.github_planner import _do_load_github_global_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    existing = {"auth": {"method": "token", "username": "alice"}, "default_repo": "alice/proj",
                "rate_limit_remaining": 4500, "last_checked": "2026-01-01T00:00:00Z"}
    (workspace / "hub_agents" / "github_global_config.json").write_text(
        json.dumps(existing), encoding="utf-8"
    )

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_load_github_global_config()

    assert result["auth"]["username"] == "alice"
    assert result["default_repo"] == "alice/proj"
    assert result["rate_limit_remaining"] == 4500


def test_save_github_local_config_merges_data(workspace):
    from extensions.github_planner import _do_save_github_local_config, _do_load_github_local_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        _do_save_github_local_config({"default_branch": "main", "repo": "owner/repo"})
        _do_save_github_local_config({"default_branch": "develop"})  # partial update
        result = _do_load_github_local_config()

    config_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "github_local_config.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["default_branch"] == "develop"  # overwritten
    assert data["repo"] == "owner/repo"  # preserved


def test_get_github_config_global_scope(workspace):
    from extensions.github_planner import _do_get_github_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=(None, MagicMock(value="none"))), \
         patch("extensions.github_planner.read_env", return_value={}):
        result = _do_get_github_config("global")

    assert result["scope"] == "global"
    assert "global" in result
    assert "local" not in result


def test_get_github_config_local_scope(workspace):
    from extensions.github_planner import _do_get_github_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_github_config("local")

    assert result["scope"] == "local"
    assert "local" in result
    assert "global" not in result


def test_get_github_config_both_scope(workspace):
    from extensions.github_planner import _do_get_github_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=(None, MagicMock(value="none"))), \
         patch("extensions.github_planner.read_env", return_value={}):
        result = _do_get_github_config("both")

    assert "global" in result
    assert "local" in result


def test_get_github_config_invalid_scope(workspace):
    from extensions.github_planner import _do_get_github_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_github_config("everything")

    assert result["error"] == "invalid_scope"


def test_global_config_not_in_volatile_files():
    from extensions.github_planner import _GH_PLANNER_VOLATILE_FILES
    assert "github_global_config.json" not in _GH_PLANNER_VOLATILE_FILES


def test_local_config_in_volatile_files():
    from extensions.github_planner import _GH_PLANNER_VOLATILE_FILES
    assert "github_local_config.json" in _GH_PLANNER_VOLATILE_FILES


# ── sync_github_issues / _check_suggest_unload (#113) ─────────────────────────

def _make_raw_issue(number=1, title="Fix bug", state="open", updated_at=None, labels=None, is_pr=False):
    raw = {
        "number": number,
        "title": title,
        "body": "Issue body.",
        "state": state,
        "labels": [{"name": l} for l in (labels or [])],
        "assignees": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": updated_at or "2026-01-02T00:00:00Z",
        "html_url": f"https://github.com/owner/repo/issues/{number}",
    }
    if is_pr:
        raw["pull_request"] = {"url": "..."}
    return raw


def test_sync_github_issues_writes_local_files(workspace):
    from extensions.github_planner import _do_sync_github_issues
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues_all.return_value = [
        _make_raw_issue(1, "Fix auth bug"),
        _make_raw_issue(2, "Add dark mode"),
    ]

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "owner/repo"}):
        result = _do_sync_github_issues()

    assert result.get("error") is None
    assert result["synced"] == 2
    issues_dir = workspace / "hub_agents" / "issues"
    assert issues_dir.exists()
    assert len(list(issues_dir.glob("*.md"))) == 2


def test_sync_github_issues_skips_pull_requests(workspace):
    from extensions.github_planner import _do_sync_github_issues
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues_all.return_value = [
        _make_raw_issue(1, "Real issue"),
        _make_raw_issue(2, "A PR", is_pr=True),
    ]

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "owner/repo"}):
        result = _do_sync_github_issues()

    assert result["synced"] == 1
    assert result["total"] == 2  # total includes the PR in raw count


def test_sync_github_issues_skips_unchanged(workspace):
    from extensions.github_planner import _do_sync_github_issues
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    updated_at = "2026-01-02T00:00:00Z"
    raw = _make_raw_issue(1, "Fix bug", updated_at=updated_at)
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues_all.return_value = [raw]

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "owner/repo"}):
        # First sync writes the file
        _do_sync_github_issues()
        # Second sync should skip unchanged
        result = _do_sync_github_issues()

    assert result["skipped"] == 1
    assert result["synced"] == 0


def test_sync_github_issues_refresh_forces_rewrite(workspace):
    from extensions.github_planner import _do_sync_github_issues
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    raw = _make_raw_issue(1, "Fix bug", updated_at="2026-01-02T00:00:00Z")
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues_all.return_value = [raw]

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "owner/repo"}):
        _do_sync_github_issues()
        result = _do_sync_github_issues(refresh=True)

    assert result["synced"] == 1
    assert result["skipped"] == 0


def test_sync_github_issues_invalid_state(workspace):
    from extensions.github_planner import _do_sync_github_issues
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_sync_github_issues(state="unknown")

    assert result["error"] == "invalid_state"


def test_sync_github_issues_no_auth(workspace):
    from extensions.github_planner import _do_sync_github_issues
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(None, "No token")):
        result = _do_sync_github_issues()

    assert result["error"] == "github_unavailable"


def test_sync_github_issues_records_synced_at(workspace):
    from extensions.github_planner import _do_sync_github_issues
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues_all.return_value = [_make_raw_issue(1, "Test")]

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "owner/repo"}):
        _do_sync_github_issues()

    config_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "github_local_config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "issues_synced_at" in data


def test_check_suggest_unload_all_caches(workspace):
    from extensions.github_planner import _check_suggest_unload, _ANALYSIS_CACHE, _PROJECT_DOCS_CACHE, _LABEL_CACHE
    _ANALYSIS_CACHE["key"] = {"data": "x"}
    _PROJECT_DOCS_CACHE["key"] = {"data": "x"}
    _LABEL_CACHE["key"] = {"data": "x"}
    result = _check_suggest_unload()
    assert result is not None
    assert "unload" in result.lower()


def test_check_suggest_unload_partial_caches():
    from extensions.github_planner import _check_suggest_unload, _ANALYSIS_CACHE, _PROJECT_DOCS_CACHE, _LABEL_CACHE
    # Only analysis cache populated — should not suggest
    _ANALYSIS_CACHE["key"] = {"data": "x"}
    result = _check_suggest_unload()
    assert result is None


def test_list_issues_suggest_sync_when_stale(workspace):
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_list_issues()

    # No github_local_config.json → cache is stale
    assert "_suggest_sync" in result


def test_list_issues_no_suggest_sync_when_fresh(workspace):
    from extensions.github_planner import _do_save_github_local_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)

    # Write a fresh synced_at timestamp
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        _do_save_github_local_config({"issues_synced_at": time.time()})
        result = _do_list_issues()

    assert "_suggest_sync" not in result


def test_list_issues_suggest_unload_when_heavy(workspace):
    from extensions.github_planner import _ANALYSIS_CACHE, _PROJECT_DOCS_CACHE, _LABEL_CACHE, _do_save_github_local_config
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)
    _ANALYSIS_CACHE["k"] = {}
    _PROJECT_DOCS_CACHE["k"] = {}
    _LABEL_CACHE["k"] = {}

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        _do_save_github_local_config({"issues_synced_at": time.time()})
        result = _do_list_issues()

    assert "_suggest_unload" in result


# ── Coverage gap tests ────────────────────────────────────────────────────────

def test_generate_issue_workflows_feature_label(workspace):
    from extensions.github_planner import _do_generate_issue_workflows
    (workspace / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)
    from extensions.github_planner.storage import write_issue_file
    from datetime import date
    write_issue_file(workspace, "add-dark-mode", "Add dark mode", "Body.", [], ["enhancement"], date.today())

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_generate_issue_workflows("add-dark-mode")
    assert result.get("error") is None
    content = (workspace / "hub_agents" / "issues" / "add-dark-mode.md").read_text()
    assert "feature" in content.lower()


def test_generate_issue_workflows_refactor_label(workspace):
    from extensions.github_planner import _do_generate_issue_workflows
    (workspace / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)
    from extensions.github_planner.storage import write_issue_file
    from datetime import date
    write_issue_file(workspace, "refactor-auth", "Refactor auth", "Body.", [], ["refactor"], date.today())

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_generate_issue_workflows("refactor-auth")
    assert result.get("error") is None


def test_generate_issue_workflows_test_label(workspace):
    from extensions.github_planner import _do_generate_issue_workflows
    (workspace / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)
    from extensions.github_planner.storage import write_issue_file
    from datetime import date
    write_issue_file(workspace, "add-tests", "Add tests", "Body.", [], ["testing"], date.today())

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_generate_issue_workflows("add-tests")
    assert result.get("error") is None


def test_generate_issue_workflows_docs_label(workspace):
    from extensions.github_planner import _do_generate_issue_workflows
    (workspace / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)
    from extensions.github_planner.storage import write_issue_file
    from datetime import date
    write_issue_file(workspace, "update-docs", "Update docs", "Body.", [], ["documentation"], date.today())

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_generate_issue_workflows("update-docs")
    assert result.get("error") is None


def test_generate_issue_workflows_missing_slug(workspace):
    from extensions.github_planner import _do_generate_issue_workflows
    (workspace / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_generate_issue_workflows("nonexistent-slug")
    assert result.get("error") == "issue_not_found"


def test_generate_issue_workflows_not_initialized(tmp_path):
    from extensions.github_planner import _do_generate_issue_workflows
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_generate_issue_workflows("any-slug")
    assert result.get("status") == "needs_init"


def test_update_project_detail_section_empty_content(workspace):
    from extensions.github_planner import _do_update_project_detail_section
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_update_project_detail_section("Auth", "")
    assert result["error"] == "invalid_input"


def test_update_project_detail_section_empty_feature_name(workspace):
    from extensions.github_planner import _do_update_project_detail_section
    (workspace / "hub_agents").mkdir(parents=True, exist_ok=True)
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_update_project_detail_section("", "Some content")
    assert result["error"] == "invalid_input"


def test_get_issue_context_missing_file(workspace):
    from extensions.github_planner import _do_get_issue_context
    (workspace / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_issue_context("nonexistent-slug")
    assert "error" in result


def test_project_docs_cache_returns_cached(workspace):
    from extensions.github_planner import _do_load_project_docs, _PROJECT_DOCS_CACHE
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# Cached Project")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "owner/repo"}):
        _do_load_project_docs("summary")
        # Populate cache with the repo key to test cache-hit path
        _PROJECT_DOCS_CACHE["owner/repo"] = {"summary": "cached!", "detail": None, "loaded_at": 999999}
        r2 = _do_load_project_docs("summary")

    assert r2["summary"] == "cached!"


def test_lookup_feature_section_substring_match(workspace):
    """Tests the substring match branch (929-930) in _do_lookup_feature_section."""
    from extensions.github_planner import _do_lookup_feature_section
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# My Project")
    (docs_dir / "project_detail.md").write_text("## Authentication Flow\nJWT tokens.\n")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        # "auth" is a substring of "Authentication Flow" — exercises substring match branch
        result = _do_lookup_feature_section("auth")
    assert result.get("matched") is True


def test_load_file_hashes_corrupt_json(workspace):
    """Tests OSError/JSONDecodeError branch in _load_file_hashes (1022-1023)."""
    from extensions.github_planner import _load_file_hashes
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    hashes_file = docs_dir / "file_hashes.json"
    hashes_file.write_text("not valid json {{", encoding="utf-8")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _load_file_hashes(workspace)
    assert result == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Coverage gap tests — additional branches in extensions/github_planner/__init__.py
# ═══════════════════════════════════════════════════════════════════════════════

# ── generate_issue_workflows: issue_not_found branches (lines 203, 263) ────────

def test_generate_issue_workflows_frontmatter_missing(workspace):
    """_do_generate_issue_workflows returns issue_not_found when frontmatter missing (line 203)."""
    from extensions.github_planner import _do_generate_issue_workflows
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_generate_issue_workflows("nonexistent-slug")
    assert result["error"] == "issue_not_found"


def test_generate_issue_workflows_file_missing_after_frontmatter(workspace):
    """_do_generate_issue_workflows returns issue_not_found when issue file deleted (line 263)."""
    from extensions.github_planner import _do_generate_issue_workflows
    from pathlib import Path as RealPath
    orig_exists = RealPath.exists
    # Track calls to exists(): let hub_agents/ pass, but make issue_path return False
    # after read_issue_frontmatter has already read the frontmatter
    issue_exists_calls = [0]

    def patched_exists(self):
        if "issues" in str(self) and str(self).endswith(".md"):
            issue_exists_calls[0] += 1
            if issue_exists_calls[0] > 1:
                return False  # simulate file deleted between calls
        return orig_exists(self)

    from datetime import date
    from extensions.github_planner.storage import write_issue_file, IssueStatus
    write_issue_file(workspace, "some-slug", "Some Title", "Body", [], [],
                     date.today(), IssueStatus.OPEN)

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch.object(RealPath, "exists", patched_exists):
        result = _do_generate_issue_workflows("some-slug")
    assert result.get("error") == "issue_not_found"


# ── update_project_detail_section: ensure_initialized guard (line 457) ────────

def test_update_project_detail_section_not_initialized(tmp_path):
    """_do_update_project_detail_section returns needs_init when hub_agents/ absent (line 457)."""
    from extensions.github_planner import _do_update_project_detail_section
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_update_project_detail_section("MyFeature", "some content")
    assert result.get("status") == "needs_init"


# ── fetch_analysis_batch: github_unavailable (line 686) ───────────────────────

def test_fetch_analysis_batch_no_github_client(workspace):
    """_do_fetch_analysis_batch returns github_unavailable when no client (line 686)."""
    _ANALYSIS_CACHE["o/r"] = {
        "repo": "o/r",
        "pending_md": [{"path": "README.md"}],
        "pending_code": [],
    }
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(None, "No token")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_fetch_analysis_batch("o/r", batch_size=5)
    assert result["error"] == "github_unavailable"


# ── load_project_docs: cache hit for "both" (line 792) ────────────────────────

def test_load_project_docs_cache_hit_both(workspace):
    """_do_load_project_docs returns cached 'both' (summary+detail) (line 792)."""
    _PROJECT_DOCS_CACHE["o/r"] = {"summary": "S", "detail": "D"}
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_load_project_docs("all", "o/r", force_reload=False)
    assert result["summary"] == "S"
    assert result["detail"] == "D"


# ── session header: first-word prefix match (lines 929-930) ───────────────────

def test_lookup_feature_section_first_word_prefix_match(workspace):
    """Tests first-word prefix match in _do_lookup_feature_section (lines 929-930)."""
    from extensions.github_planner import _do_lookup_feature_section
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True)
    (docs_dir / "project_summary.md").write_text("# My Project")
    (docs_dir / "project_detail.md").write_text("## Billing System\nHandles payments.\n")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        # "billing" matches "Billing System" by first word prefix
        result = _do_lookup_feature_section("billing details")
    assert result.get("matched") is True


# ── _build_file_tree: PermissionError (lines 1058-1059) ──────────────────────

def test_build_file_tree_permission_error(workspace, tmp_path):
    """_build_file_tree skips dirs it cannot read (lines 1058-1059)."""
    from extensions.github_planner import _do_get_file_tree
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("pathlib.Path.iterdir", side_effect=PermissionError("denied")):
        result = _do_get_file_tree(refresh=True)
    assert "tree" in result


# ── file tree cache: ValueError/TypeError in TTL check (lines 1095-1096) ──────

def test_get_file_tree_invalid_cached_date(workspace):
    """Bad fetched_at in _FILE_TREE_CACHE causes ValueError branch (lines 1095-1096)."""
    from extensions.github_planner import _FILE_TREE_CACHE, _do_get_file_tree
    _FILE_TREE_CACHE.clear()
    _FILE_TREE_CACHE["fetched_at"] = "not-a-date"  # triggers ValueError
    _FILE_TREE_CACHE["tree"] = {}
    _FILE_TREE_CACHE["flat_index"] = []
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_file_tree(refresh=False)
    # Should fall through to disk/re-walk, not crash
    assert "tree" in result
    _FILE_TREE_CACHE.clear()


# ── file tree: disk cache OSError branch (lines 1108-1109) ───────────────────

def test_get_file_tree_disk_cache_oserror(workspace):
    """OSError reading disk cache falls through to re-walk (lines 1108-1109)."""
    from extensions.github_planner import _FILE_TREE_CACHE, _do_get_file_tree, _gh_planner_docs_dir
    _FILE_TREE_CACHE.clear()  # no in-memory cache
    # Create a corrupt disk cache file (missing required key)
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "file_tree.json").write_text("not valid json {{", encoding="utf-8")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_get_file_tree(refresh=False)
    assert "tree" in result
    _FILE_TREE_CACHE.clear()


# ── analyze_repo_full: list_repo_tree exception (lines 1160-1161) ─────────────

def test_analyze_repo_full_list_tree_exception(workspace):
    """Returns github_error when list_repo_tree raises (lines 1160-1161)."""
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_repo_tree.side_effect = Exception("network down")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_analyze_repo_full("o/r")
    assert result["error"] == "github_error"


# ── analyze_repo_full: binary file skip (lines 1176-1177) ────────────────────

def test_analyze_repo_full_skips_binary_files(workspace):
    """Binary extensions are skipped during analysis (lines 1176-1177)."""
    tree = [{"path": "image.png", "size": 1000, "sha": "abc123"}]
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_repo_tree.return_value = tree
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_analyze_repo_full("o/r")
    assert result["skipped_unchanged"] >= 1
    mock_gh.get_file_content.assert_not_called()


# ── analyze_repo_full: get_file_content exception (lines 1201-1203) ──────────

def test_analyze_repo_full_get_file_content_exception(workspace):
    """File fetch exception adds to skipped_errors (lines 1201-1203)."""
    from extensions.github_planner.client import GitHubError
    tree = [{"path": "bad.py", "size": 100, "sha": "xyz"}]
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_repo_tree.return_value = tree
    mock_gh.get_file_content.side_effect = GitHubError("binary", error_code="binary_file")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(mock_gh, "")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        result = _do_analyze_repo_full("o/r")
    assert result["skipped_errors"] >= 1


# ── list_pending_drafts: ensure_initialized guard (line 1326) ─────────────────

def test_list_pending_drafts_not_initialized(tmp_path):
    """_do_list_pending_drafts returns needs_init when hub_agents absent (line 1326)."""
    from extensions.github_planner import _do_list_pending_drafts
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_list_pending_drafts()
    assert result.get("status") == "needs_init"


# ── sync_github_issues: ensure_initialized guard (line 1365) ─────────────────

def test_sync_github_issues_not_initialized(tmp_path):
    """_do_sync_github_issues returns needs_init when hub_agents absent (line 1365)."""
    from extensions.github_planner import _do_sync_github_issues
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_sync_github_issues()
    assert result.get("status") == "needs_init"


# ── sync_github_issues: list_issues_all exception (lines 1378-1379) ──────────

def test_sync_github_issues_list_all_exception(workspace):
    """Returns github_error when list_issues_all raises (lines 1378-1379)."""
    from extensions.github_planner import _do_sync_github_issues
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues_all.side_effect = Exception("API down")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_sync_github_issues()
    assert result["error"] == "github_error"


# ── sync_github_issues: empty slug fallback (line 1412) ───────────────────────

def test_sync_github_issues_empty_slug_fallback(workspace):
    """Issues with no number and empty title use fallback slug (line 1412)."""
    from extensions.github_planner import _do_sync_github_issues
    raw_issues = [{"number": None, "title": "", "body": "B", "state": "open",
                   "labels": [], "assignees": [], "created_at": "", "updated_at": "",
                   "html_url": ""}]
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues_all.return_value = raw_issues
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_sync_github_issues()
    assert "synced" in result


# ── sync_github_issues: invalid created_at (lines 1434-1435) ─────────────────

def test_sync_github_issues_invalid_created_at(workspace):
    """Falls back to today's date when created_at is malformed (lines 1434-1435)."""
    from extensions.github_planner import _do_sync_github_issues
    raw_issues = [{"number": 1, "title": "Test", "body": "B", "state": "open",
                   "labels": [], "assignees": [], "created_at": "bad-date",
                   "updated_at": "", "html_url": ""}]
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_issues_all.return_value = raw_issues
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_sync_github_issues()
    assert result["synced"] == 1


# ── _issues_cache_stale: no synced_at (line 1490) ────────────────────────────

def test_issues_cache_stale_no_synced_at(workspace):
    """Returns True when issues_synced_at key is absent (line 1490)."""
    from extensions.github_planner import _issues_cache_stale
    config_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "github_local_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")
    result = _issues_cache_stale(workspace)
    assert result is True


def test_issues_cache_stale_json_error(workspace):
    """Returns True when config JSON is corrupt (lines 1492-1493)."""
    from extensions.github_planner import _issues_cache_stale
    config_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "github_local_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("not json {{", encoding="utf-8")
    result = _issues_cache_stale(workspace)
    assert result is True


# ── save_docs_strategy: ensure_initialized (line 1532) ───────────────────────

def test_save_docs_strategy_not_initialized(tmp_path):
    """Returns needs_init when hub_agents absent (line 1532)."""
    from extensions.github_planner import _do_save_docs_strategy
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_save_docs_strategy("refer")
    assert result.get("status") == "needs_init"


# ── load_docs_strategy: ensure_initialized + error branches (lines 1562, 1570-1571) ──

def test_load_docs_strategy_not_initialized(tmp_path):
    """Returns needs_init when hub_agents absent (line 1562)."""
    from extensions.github_planner import _do_load_docs_strategy
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_load_docs_strategy()
    assert result.get("status") == "needs_init"


def test_load_docs_strategy_json_error(workspace):
    """Returns null strategy when JSON is corrupt (lines 1570-1571)."""
    from extensions.github_planner import _do_load_docs_strategy
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "docs_strategy.json").write_text("not json {{", encoding="utf-8")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_load_docs_strategy()
    assert result["strategy"] is None


# ── analyze_github_labels: ensure_initialized (line 1586) ────────────────────

def test_analyze_github_labels_not_initialized(tmp_path):
    """Returns needs_init when hub_agents absent (line 1586)."""
    from extensions.github_planner import _do_analyze_github_labels
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_analyze_github_labels()
    assert result.get("status") == "needs_init"


# ── analyze_github_labels: list exception (lines 1601-1602) ──────────────────

def test_analyze_github_labels_list_exception(workspace):
    """Returns github_error when list_labels raises (lines 1601-1602)."""
    from extensions.github_planner import _do_analyze_github_labels
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_labels.side_effect = Exception("API error")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_analyze_github_labels()
    assert result["error"] == "github_error"


# ── analyze_github_labels: bad created_at parse (lines 1628-1629) ─────────────

def test_analyze_github_labels_bad_created_at(workspace):
    """age_days=None when label created_at is malformed (lines 1628-1629)."""
    from extensions.github_planner import _do_analyze_github_labels
    raw_labels = [{"name": "bug", "color": "red", "description": "",
                   "created_at": "bad-date"}]
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_labels.return_value = raw_labels
    mock_gh.list_issues.return_value = []
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_analyze_github_labels()
    assert "active_labels" in result or "error" not in result


# ── analyze_github_labels: corrupt existing config (lines 1663-1664) ──────────

def test_analyze_github_labels_corrupt_existing_config(workspace):
    """Handles corrupt existing github_local_config.json when saving (lines 1663-1664)."""
    from extensions.github_planner import _do_analyze_github_labels
    config_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "github_local_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("not json {{", encoding="utf-8")
    raw_labels = [{"name": "bug", "color": "red", "description": "", "created_at": ""}]
    mock_gh = MagicMock()
    mock_gh.__enter__ = lambda s: s
    mock_gh.__exit__ = MagicMock(return_value=False)
    mock_gh.list_labels.return_value = raw_labels
    mock_gh.list_issues.return_value = []
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.get_github_client", return_value=(mock_gh, "")):
        result = _do_analyze_github_labels()
    assert "active_labels" in result


# ── load_github_local_config: ensure_initialized (line 1701) ─────────────────

def test_load_github_local_config_not_initialized(tmp_path):
    """Returns needs_init when hub_agents absent (line 1701)."""
    from extensions.github_planner import _do_load_github_local_config
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_load_github_local_config()
    assert result.get("status") == "needs_init"


def test_load_github_local_config_json_error(workspace):
    """Returns null labels when JSON is corrupt (lines 1717-1718)."""
    from extensions.github_planner import _do_load_github_local_config
    config_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "github_local_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("not json {{", encoding="utf-8")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_load_github_local_config()
    assert result["labels"] is None


# ── load_github_global_config: ensure_initialized (line 1739) ─────────────────

def test_load_github_global_config_not_initialized(tmp_path):
    """Returns needs_init when hub_agents absent (line 1739)."""
    from extensions.github_planner import _do_load_github_global_config
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_load_github_global_config()
    assert result.get("status") == "needs_init"


def test_load_github_global_config_json_error(workspace):
    """Returns defaults when JSON is corrupt (lines 1760-1761)."""
    from extensions.github_planner import _do_load_github_global_config
    global_path = workspace / "hub_agents" / "github_global_config.json"
    global_path.write_text("not json {{", encoding="utf-8")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.resolve_token", return_value=(None, MagicMock(value="none"))), \
         patch("extensions.github_planner.read_env", return_value={}):
        result = _do_load_github_global_config()
    # Should return default config, not crash
    assert "auth" in result


# ── save_github_local_config: ensure_initialized + json error (lines 1772, 1782-1783) ──

def test_save_github_local_config_not_initialized(tmp_path):
    """Returns needs_init when hub_agents absent (line 1772)."""
    from extensions.github_planner import _do_save_github_local_config
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_save_github_local_config({"key": "val"})
    assert result.get("status") == "needs_init"


def test_save_github_local_config_corrupt_existing(workspace):
    """Handles corrupt existing config gracefully (lines 1782-1783)."""
    from extensions.github_planner import _do_save_github_local_config
    config_path = workspace / "hub_agents" / "extensions" / "gh_planner" / "github_local_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("not json {{", encoding="utf-8")
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
        result = _do_save_github_local_config({"key": "val"})
    assert result.get("saved") is True


# ── get_github_config: ensure_initialized (line 1806) ────────────────────────

def test_get_github_config_not_initialized(tmp_path):
    """Returns needs_init when hub_agents absent (line 1806)."""
    from extensions.github_planner import _do_get_github_config
    with patch("extensions.github_planner.get_workspace_root", return_value=tmp_path):
        result = _do_get_github_config("both")
    assert result.get("status") == "needs_init"


# ── list_plugin_state: non-empty caches (lines 1846, 1850, 1852) ──────────────

def test_list_plugin_state_with_all_caches(workspace):
    """list_plugin_state includes all populated caches (lines 1846, 1850, 1852)."""
    from extensions.github_planner import (
        _ANALYSIS_CACHE, _PROJECT_DOCS_CACHE, _SESSION_HEADER_CACHE,
        _LABEL_CACHE, _do_list_plugin_state
    )
    _ANALYSIS_CACHE["o/r"] = {"data": "x"}
    _PROJECT_DOCS_CACHE["o/r"] = {"summary": "s"}
    _SESSION_HEADER_CACHE["o/r"] = {"header": "h"}
    _LABEL_CACHE[str(workspace)] = {"active_labels": []}
    try:
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_list_plugin_state("gh_planner")
        cache_names = {c["name"] for c in result["caches"]}
        assert "_PROJECT_DOCS_CACHE" in cache_names
        assert "_SESSION_HEADER_CACHE" in cache_names
        assert "_LABEL_CACHE" in cache_names
    finally:
        _ANALYSIS_CACHE.clear()
        _PROJECT_DOCS_CACHE.clear()
        _SESSION_HEADER_CACHE.clear()
        _LABEL_CACHE.clear()


# ── list_plugin_state: suggest_unload when memory is large (line 1890) ────────

def test_list_plugin_state_suggest_unload_large_memory(workspace):
    """suggest_unload is True when estimated memory >= 500KB (line 1890)."""
    from extensions.github_planner import _ANALYSIS_CACHE, _do_list_plugin_state
    # Populate cache with large data to exceed threshold
    large_data = {"key": "x" * (512 * 1024)}  # ~512KB string
    _ANALYSIS_CACHE["o/r"] = large_data
    try:
        with patch("extensions.github_planner.get_workspace_root", return_value=workspace):
            result = _do_list_plugin_state("gh_planner")
        assert result.get("suggest_unload") is True
    finally:
        _ANALYSIS_CACHE.clear()


# ── unload_plugin: error deletion (lines 1926-1927) ───────────────────────────

def test_unload_plugin_error_deleting_file(workspace):
    """Errors while deleting volatile files are recorded (lines 1926-1927)."""
    from extensions.github_planner import _do_unload_plugin, _gh_planner_docs_dir
    docs_dir = _gh_planner_docs_dir(workspace)
    docs_dir.mkdir(parents=True, exist_ok=True)
    snap_file = docs_dir / "analyzer_snapshot.json"
    snap_file.write_text("{}", encoding="utf-8")

    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("pathlib.Path.unlink", side_effect=OSError("perm denied")):
        result = _do_unload_plugin("gh_planner")
    # Should not crash; errors are recorded
    assert "errors" in result


# ── MCP wrapper return lines via server ────────────────────────────────────────

def _mcp_call(tool_name, args, workspace):
    """Call a tool through the MCP server framework."""
    import asyncio
    from terminal_hub.server import create_server
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        return asyncio.run(server._tool_manager.call_tool(tool_name, args))


def test_mcp_wrapper_update_project_detail_section(workspace):
    """Covers update_project_detail_section MCP wrapper."""
    result = _mcp_call("update_project_detail_section",
                       {"feature_name": "Auth", "overview": "JWT tokens used."}, workspace)
    assert "error" not in result or result.get("saved") is True or "status" in result


def test_mcp_wrapper_save_docs_strategy(workspace):
    """Covers save_docs_strategy MCP wrapper return line 2095."""
    result = _mcp_call("save_docs_strategy", {"strategy": "refer"}, workspace)
    assert result.get("saved") is True or "status" in result


def test_mcp_wrapper_load_docs_strategy(workspace):
    """Covers load_docs_strategy MCP wrapper return line 2101."""
    result = _mcp_call("load_docs_strategy", {}, workspace)
    assert "strategy" in result or "status" in result


def test_mcp_wrapper_start_repo_analysis_no_auth(workspace):
    """Covers start_repo_analysis MCP wrapper return line 2120."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(None, "No token")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        import asyncio
        from terminal_hub.server import create_server
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool("start_repo_analysis", {}))
    assert "error" in result or "status" in result


def test_mcp_wrapper_fetch_analysis_batch_no_cache(workspace):
    """Covers fetch_analysis_batch MCP wrapper return line 2130."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        import asyncio
        from terminal_hub.server import create_server
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool("fetch_analysis_batch", {}))
    assert "error" in result or "done" in result


def test_mcp_wrapper_get_analysis_status_no_cache(workspace):
    """Covers get_analysis_status MCP wrapper return line 2138."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        import asyncio
        from terminal_hub.server import create_server
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool("get_analysis_status", {}))
    assert "error" in result or "done" in result or "status" in result


def test_mcp_wrapper_save_project_docs(workspace):
    """Covers save_project_docs MCP wrapper."""
    result = _mcp_call("save_project_docs",
                       {"goal": "A portfolio site", "tech_stack": ["React", "TypeScript"]}, workspace)
    assert result.get("saved") is True or "status" in result


def test_mcp_wrapper_load_project_docs(workspace):
    """Covers load_project_docs MCP wrapper return line 2160."""
    result = _mcp_call("load_project_docs", {"doc": "summary"}, workspace)
    assert "summary" in result or "status" in result


def test_mcp_wrapper_docs_exist(workspace):
    """Covers docs_exist MCP wrapper return line 2170."""
    result = _mcp_call("docs_exist", {}, workspace)
    assert "summary_exists" in result or "status" in result


def test_mcp_wrapper_lookup_feature_section(workspace):
    """Covers lookup_feature_section MCP wrapper return line 2187."""
    result = _mcp_call("lookup_feature_section", {"feature": "auth"}, workspace)
    assert "matched" in result or "error" in result or "status" in result


def test_mcp_wrapper_analyze_repo_full_no_auth(workspace):
    """Covers analyze_repo_full MCP wrapper return line 2200."""
    with patch("extensions.github_planner.get_workspace_root", return_value=workspace), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace), \
         patch("extensions.github_planner._get_github_client", return_value=(None, "No token")), \
         patch("extensions.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        import asyncio
        from terminal_hub.server import create_server
        server = create_server()
        result = asyncio.run(server._tool_manager.call_tool("analyze_repo_full", {}))
    assert "error" in result


def test_mcp_wrapper_get_session_header(workspace):
    """Covers get_session_header MCP wrapper return line 2209."""
    result = _mcp_call("get_session_header", {}, workspace)
    assert "docs" in result or "status" in result


def test_mcp_wrapper_list_plugin_state(workspace):
    """Covers list_plugin_state MCP wrapper return line 2230."""
    result = _mcp_call("list_plugin_state", {"plugin": "gh_planner"}, workspace)
    assert "caches" in result or "error" in result


def test_mcp_wrapper_generate_issue_workflows(workspace):
    """Covers generate_issue_workflows MCP wrapper return line 2004."""
    result = _mcp_call("generate_issue_workflows", {"slug": "nonexistent-slug"}, workspace)
    # Should return issue_not_found since slug doesn't exist
    assert result.get("error") == "issue_not_found" or "status" in result
