"""The installation must be read-only at runtime (R24).

Production code once wrote per-project data into the plugin's own directory:
milestone labels into labels.json, user-created skills and their registry row
into skills/. Both are tracked files, so running the suite edited the working
tree — and a test's result depended on a file that same test had rewritten.

These tests pin the boundary rather than the specific fix.
"""
import pytest

from extensions.gh_management.github_planner.skills import _PLUGIN_DIR

# Files shipped with the package that runtime must treat as reference data.
_READ_ONLY = [
    _PLUGIN_DIR / "labels.json",
    _PLUGIN_DIR / "skills" / "SKILLS.md",
    _PLUGIN_DIR / "unload_policy.json",
]


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "hub_agents" / "issues").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def shipped_bytes():
    return {p: p.read_bytes() for p in _READ_ONLY if p.exists()}


def test_creating_a_milestone_label_leaves_shipped_files_untouched(workspace, shipped_bytes):
    from unittest.mock import MagicMock, patch

    gh = MagicMock()
    gh.__enter__ = lambda s: s
    gh.__exit__ = MagicMock(return_value=False)
    gh.get_labels.return_value = set()

    with patch("extensions.gh_management.github_planner.get_workspace_root", return_value=workspace), \
         patch("extensions.gh_management.github_planner.get_github_client", return_value=(gh, None)), \
         patch("extensions.gh_management.github_planner.read_env", return_value={"GITHUB_REPO": "o/r"}):
        from extensions.gh_management.github_planner import _ensure_milestone_label
        _ensure_milestone_label(3, "Third milestone")

    for path, before in shipped_bytes.items():
        assert path.read_bytes() == before, f"{path.name} was modified at runtime"


def test_creating_a_skill_leaves_shipped_files_untouched(workspace, shipped_bytes):
    from extensions.gh_management.github_planner import _do_update_skill_create

    _do_update_skill_create(
        root=workspace,
        name="guard-check-skill",
        description="Written by the install-tree guard test.",
        content_hints=["guarding"],
        source_doc=None,
        dry_run=False,
    )

    assert (workspace / "hub_agents" / "skills" / "guard-check-skill.md").exists()
    for path, before in shipped_bytes.items():
        assert path.read_bytes() == before, f"{path.name} was modified at runtime"
