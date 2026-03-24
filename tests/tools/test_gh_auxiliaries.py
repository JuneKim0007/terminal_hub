"""Tests for gh_auxiliaries — metadata extraction, template rendering, file writing."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from extensions.gh_auxiliaries import (
    _insert_coc_link,
    _scan_codeowners,
    _scan_package_json,
    _scan_pyproject,
    _scan_readme,
    load_community_metadata,
    scan_project_metadata,
    _do_scan_community_metadata,
    _do_save_community_metadata,
    _do_generate_and_write_coc,
    _do_link_community_file,
    _TEMPLATE_URLS,
    _TEMPLATE_NAMES,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """Return a temp dir that looks like a project root."""
    (tmp_path / "hub_agents").mkdir()
    return tmp_path


# ── _scan_pyproject ───────────────────────────────────────────────────────────

def test_scan_pyproject_pep621(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "myproject"\nauthors = [{name = "Alice", email = "alice@example.com"}]\n'
    )
    result = _scan_pyproject(tmp_path)
    assert result["project_name"] == "myproject"
    assert result["maintainer_name"] == "Alice"
    assert result["contact_email"] == "alice@example.com"


def test_scan_pyproject_missing(tmp_path: Path) -> None:
    assert _scan_pyproject(tmp_path) == {}


def test_scan_pyproject_corrupt(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("not valid toml ::::")
    assert _scan_pyproject(tmp_path) == {}


def test_scan_pyproject_poetry_inline_author(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "mylib"\nauthors = ["Bob <bob@example.com>"]\n'
    )
    result = _scan_pyproject(tmp_path)
    assert result["project_name"] == "mylib"
    assert result["maintainer_name"] == "Bob"
    assert result["contact_email"] == "bob@example.com"


# ── _scan_package_json ────────────────────────────────────────────────────────

def test_scan_package_json_with_author_object(tmp_path: Path) -> None:
    data = {"name": "my-app", "author": {"name": "Carol", "email": "carol@example.com"}}
    (tmp_path / "package.json").write_text(json.dumps(data))
    result = _scan_package_json(tmp_path)
    assert result["project_name"] == "my-app"
    assert result["maintainer_name"] == "Carol"
    assert result["contact_email"] == "carol@example.com"


def test_scan_package_json_author_string(tmp_path: Path) -> None:
    data = {"name": "pkg", "author": "Dave <dave@example.com>"}
    (tmp_path / "package.json").write_text(json.dumps(data))
    result = _scan_package_json(tmp_path)
    assert result["maintainer_name"] == "Dave"
    assert result["contact_email"] == "dave@example.com"


def test_scan_package_json_bugs_email_fallback(tmp_path: Path) -> None:
    data = {"name": "pkg", "bugs": {"email": "bugs@example.com"}}
    (tmp_path / "package.json").write_text(json.dumps(data))
    result = _scan_package_json(tmp_path)
    assert result["contact_email"] == "bugs@example.com"


def test_scan_package_json_missing(tmp_path: Path) -> None:
    assert _scan_package_json(tmp_path) == {}


# ── _scan_codeowners ─────────────────────────────────────────────────────────

def test_scan_codeowners_github_dir(tmp_path: Path) -> None:
    gh = tmp_path / ".github"
    gh.mkdir()
    (gh / "CODEOWNERS").write_text("* @org/team\n")
    result = _scan_codeowners(tmp_path)
    assert result["maintainer_name"] == "org/team"


def test_scan_codeowners_missing(tmp_path: Path) -> None:
    assert _scan_codeowners(tmp_path) == {}


def test_scan_codeowners_comment_lines_skipped(tmp_path: Path) -> None:
    gh = tmp_path / ".github"
    gh.mkdir()
    (gh / "CODEOWNERS").write_text("# comment\n* @maintainer\n")
    result = _scan_codeowners(tmp_path)
    assert result["maintainer_name"] == "maintainer"


# ── _scan_readme ─────────────────────────────────────────────────────────────

def test_scan_readme_h1(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# My Cool Project\n\nDescription here.\n")
    result = _scan_readme(tmp_path)
    assert result["project_name"] == "My Cool Project"


def test_scan_readme_missing(tmp_path: Path) -> None:
    assert _scan_readme(tmp_path) == {}


# ── scan_project_metadata ─────────────────────────────────────────────────────

def test_scan_project_metadata_merges_sources(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "proj"\nauthors = [{name = "Eve", email = "eve@example.com"}]\n'
    )
    result = scan_project_metadata(tmp_path)
    meta = result["metadata"]
    assert meta["project_name"] == "proj"
    assert meta["enforcement_contact"] == meta["contact_email"]


def test_scan_project_metadata_no_files(tmp_path: Path) -> None:
    result = scan_project_metadata(tmp_path)
    assert result["metadata"] == {}
    assert result["sources"] == {}


# ── community.json persistence ────────────────────────────────────────────────

def test_load_community_metadata_missing(tmp_root: Path) -> None:
    assert load_community_metadata(tmp_root) is None


def test_save_and_load_community_metadata(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("extensions.gh_auxiliaries.resolve_workspace_root", lambda: tmp_root)
    result = _do_save_community_metadata(
        project_name="proj",
        contact_email="x@example.com",
    )
    assert result["metadata"]["project_name"] == "proj"
    assert result["metadata"]["enforcement_contact"] == "x@example.com"
    loaded = load_community_metadata(tmp_root)
    assert loaded is not None
    assert loaded["project_name"] == "proj"


def test_save_community_metadata_merges_existing(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("extensions.gh_auxiliaries.resolve_workspace_root", lambda: tmp_root)
    _do_save_community_metadata(project_name="proj", contact_email="a@example.com")
    _do_save_community_metadata(maintainer_name="Frank")
    loaded = load_community_metadata(tmp_root)
    assert loaded is not None
    assert loaded["project_name"] == "proj"
    assert loaded["maintainer_name"] == "Frank"


def test_save_community_metadata_explicit_enforcement_contact(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("extensions.gh_auxiliaries.resolve_workspace_root", lambda: tmp_root)
    _do_save_community_metadata(
        contact_email="contact@example.com",
        enforcement_contact="enforce@example.com",
    )
    loaded = load_community_metadata(tmp_root)
    assert loaded is not None
    assert loaded["enforcement_contact"] == "enforce@example.com"


# ── generate_and_write_coc ────────────────────────────────────────────────────

def test_generate_and_write_coc_unknown_template(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("extensions.gh_auxiliaries.resolve_workspace_root", lambda: tmp_root)
    result = _do_generate_and_write_coc("z", "proj", "x@example.com")
    assert result["error"] == "unknown_template"


def test_generate_and_write_coc_invalid_filename(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("extensions.gh_auxiliaries.resolve_workspace_root", lambda: tmp_root)
    result = _do_generate_and_write_coc("a", "proj", "x@example.com", filename="sub/dir.md")
    assert result["error"] == "invalid_filename"


def test_generate_and_write_coc_fetch_failed(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("extensions.gh_auxiliaries.resolve_workspace_root", lambda: tmp_root)
    monkeypatch.setattr("extensions.gh_auxiliaries._fetch_url", lambda *_a, **_kw: None)
    result = _do_generate_and_write_coc("a", "proj", "x@example.com")
    assert result["error"] == "fetch_failed"


def test_generate_and_write_coc_writes_file(tmp_root: Path, monkeypatch) -> None:
    fake_template = "Hello {{project_name}}! Contact [INSERT CONTACT METHOD]."
    monkeypatch.setattr("extensions.gh_auxiliaries.resolve_workspace_root", lambda: tmp_root)
    monkeypatch.setattr("extensions.gh_auxiliaries._fetch_url", lambda *_a, **_kw: fake_template)
    result = _do_generate_and_write_coc(
        "a", "MyProject", "hello@example.com", "enforce@example.com"
    )
    assert "path" in result
    written = Path(result["path"]).read_text()
    assert "MyProject" in written
    assert "enforce@example.com" in written
    assert "{{project_name}}" not in written
    assert "[INSERT CONTACT METHOD]" not in written


def test_generate_and_write_coc_all_template_keys(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("extensions.gh_auxiliaries.resolve_workspace_root", lambda: tmp_root)
    monkeypatch.setattr("extensions.gh_auxiliaries._fetch_url", lambda *_a, **_kw: "template text")
    for key in ("a", "b", "c"):
        result = _do_generate_and_write_coc(key, "P", "p@example.com")
        assert "error" not in result, f"Template '{key}' failed: {result}"


# ── _insert_coc_link ──────────────────────────────────────────────────────────

def test_insert_coc_link_appends_section(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# My Project\n\nSome content.\n")
    status = _insert_coc_link(readme, "CODE_OF_CONDUCT.md")
    assert status == "linked"
    text = readme.read_text()
    assert "CODE_OF_CONDUCT.md" in text
    assert "## Code of Conduct" in text


def test_insert_coc_link_already_linked(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Proj\n\nSee [Code of Conduct](CODE_OF_CONDUCT.md).\n")
    status = _insert_coc_link(readme, "CODE_OF_CONDUCT.md")
    assert status == "already linked"


def test_insert_coc_link_file_not_found(tmp_path: Path) -> None:
    status = _insert_coc_link(tmp_path / "NONEXISTENT.md", "CODE_OF_CONDUCT.md")
    assert status == "file not found"


# ── _do_link_community_file ───────────────────────────────────────────────────

def test_do_link_community_file_unknown_target(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("extensions.gh_auxiliaries.resolve_workspace_root", lambda: tmp_root)
    result = _do_link_community_file(["wiki"], "CODE_OF_CONDUCT.md")
    assert "skipped" in result["results"]["wiki"]


def test_do_link_community_file_readme(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("extensions.gh_auxiliaries.resolve_workspace_root", lambda: tmp_root)
    (tmp_root / "README.md").write_text("# Proj\n")
    result = _do_link_community_file(["readme"], "CODE_OF_CONDUCT.md")
    assert result["results"]["readme"] == "linked"


# ── Template URL and name registry ────────────────────────────────────────────

def test_template_urls_all_keys_present() -> None:
    for key in ("a", "b", "c"):
        assert key in _TEMPLATE_URLS, f"Missing URL for template '{key}'"
        assert key in _TEMPLATE_NAMES, f"Missing name for template '{key}'"


def test_template_urls_are_https() -> None:
    for key, url in _TEMPLATE_URLS.items():
        assert url.startswith("https://"), f"Template '{key}' URL must use HTTPS: {url}"
