"""Tests for cross-plugin interface layer (#132)."""
import json
from pathlib import Path


def test_gh_implementation_cache_keys_subset_of_gh_planner():
    """All cache keys used by gh_implementation must be defined in gh_planner's policy."""
    planner_policy = json.loads(
        (Path(__file__).parents[2] / "extensions/gh_management/github_planner/unload_policy.json").read_text()
    )
    impl_policy = json.loads(
        (Path(__file__).parents[2] / "extensions/gh_management/gh_implementation/unload_policy.json").read_text()
    )
    planner_keys = set(planner_policy["cache_keys"].keys())
    for cmd_name, cmd_entry in impl_policy["commands"].items():
        for key in cmd_entry.get("unload", []):
            assert key in planner_keys, f"gh_implementation command '{cmd_name}' unloads unknown key '{key}'"
        for key in cmd_entry.get("keep", []):
            assert key in planner_keys or key in impl_policy.get("cache_keys", {}), \
                f"gh_implementation command '{cmd_name}' keeps unknown key '{key}'"


def test_gh_planner_has_gh_implementation_commands():
    """apply_unload_policy must handle gh-implementation commands (defined in gh_planner policy)."""
    planner_policy = json.loads(
        (Path(__file__).parents[2] / "extensions/gh_management/github_planner/unload_policy.json").read_text()
    )
    assert "gh-implementation" in planner_policy["commands"]
    assert "gh-implementation/implement" in planner_policy["commands"]


def test_description_json_interface_block_valid():
    """gh_implementation description.json must have a valid interface block."""
    desc = json.loads(
        (Path(__file__).parents[2] / "extensions/gh_management/gh_implementation/description.json").read_text()
    )
    assert "interface" in desc
    iface = desc["interface"]
    assert "unloads_on_entry" in iface
    assert "preserves_on_entry" in iface
    assert isinstance(iface["unloads_on_entry"], list)
    assert isinstance(iface["preserves_on_entry"], list)
    assert "project_summary" in iface["preserves_on_entry"]
    assert "project_detail" in iface["preserves_on_entry"]
