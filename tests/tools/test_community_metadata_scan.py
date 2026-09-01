"""Tests for scan_community_metadata — reads project identity from manifests."""
import json
from unittest.mock import patch

import pytest

from extensions.gh_auxiliaries import _do_scan_community_metadata, scan_project_metadata


@pytest.fixture
def scan(tmp_path):
    def run():
        with patch("extensions.gh_auxiliaries.resolve_workspace_root", return_value=tmp_path):
            return _do_scan_community_metadata()
    return run


def test_merges_metadata_from_every_manifest(tmp_path, scan):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "my-api"\n', encoding="utf-8"
    )
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "CODEOWNERS").write_text("* @alice\n", encoding="utf-8")

    result = scan()

    assert result["metadata"]["project_name"] == "my-api"
    assert result["metadata"]["maintainer_name"] == "alice"
    assert "pyproject.toml" in result["sources"]
    assert ".github/CODEOWNERS" in result["sources"]
    assert "From `pyproject.toml`" in result["_display"]


def test_enforcement_contact_defaults_to_the_contact_email(tmp_path):
    """A project that names one contact gets it used for enforcement too."""
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "web-ui", "author": {"email": "dev@example.com"}}),
        encoding="utf-8",
    )
    merged = scan_project_metadata(tmp_path)["metadata"]

    assert merged["contact_email"] == "dev@example.com"
    assert merged["enforcement_contact"] == "dev@example.com"


def test_saved_metadata_fills_gaps_the_scan_could_not(tmp_path, scan):
    """Previously saved answers supplement the scan without overriding it."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "my-api"\n', encoding="utf-8")
    saved = tmp_path / "hub_agents" / "community.json"
    saved.parent.mkdir(parents=True)
    saved.write_text(
        json.dumps({"project_name": "SHOULD NOT WIN", "contact_email": "saved@example.com"}),
        encoding="utf-8",
    )

    result = scan()

    assert result["metadata"]["project_name"] == "my-api", "the live scan wins"
    assert result["metadata"]["contact_email"] == "saved@example.com", "gaps are filled"


def test_reports_when_nothing_could_be_found(scan):
    result = scan()

    assert result["metadata"] == {}
    assert "No metadata found" in result["_display"]
