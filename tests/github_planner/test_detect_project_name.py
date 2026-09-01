"""Tests for _detect_project_name — reads the project name from a manifest."""
import json

from extensions.gh_management.github_planner.session import _detect_project_name


def test_reads_the_pep621_project_name(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "my-api"\n', encoding="utf-8")
    assert _detect_project_name(tmp_path) == "my-api"


def test_falls_back_to_the_poetry_name(tmp_path):
    """A poetry-only pyproject has no [project] table."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "legacy-svc"\n', encoding="utf-8"
    )
    assert _detect_project_name(tmp_path) == "legacy-svc"


def test_reads_package_json_when_there_is_no_pyproject(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "web-ui"}), encoding="utf-8")
    assert _detect_project_name(tmp_path) == "web-ui"


def test_returns_none_when_no_manifest_is_readable(tmp_path):
    """A malformed manifest is treated as absent, not raised."""
    (tmp_path / "pyproject.toml").write_text("not : valid : toml [", encoding="utf-8")
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    assert _detect_project_name(tmp_path) is None
