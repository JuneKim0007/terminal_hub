"""Tests for cross-plugin interface layer (#132)."""
import json
from pathlib import Path


def test_gh_implementation_cache_keys_subset_of_gh_planner():
    """All keys used by gh-implementation commands must be defined in gh_planner's cache_keys.

    gh_implementation no longer has its own unload_policy.json — all commands
    (including gh-implementation and gh-implementation/implement) are defined in
    the single authoritative github_planner/unload_policy.json.
    """
    planner_policy = json.loads(
        (Path(__file__).parents[2] / "extensions/gh_management/github_planner/unload_policy.json").read_text()
    )
    known_keys = set(planner_policy["cache_keys"].keys())
    impl_commands = {
        name: entry
        for name, entry in planner_policy["commands"].items()
        if name.startswith("gh-implementation")
    }
    assert impl_commands, "Expected at least one gh-implementation command in planner policy"
    for cmd_name, cmd_entry in impl_commands.items():
        for key in cmd_entry.get("unload", []) + cmd_entry.get("keep", []):
            assert key in known_keys, (
                f"gh_planner policy command '{cmd_name}' references unknown cache key '{key}'"
            )


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
