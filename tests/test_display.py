"""Tests for terminal_hub.display — predefined_text.json lookup and formatting."""
import pytest
from unittest.mock import patch
import json


# ── helpers ───────────────────────────────────────────────────────────────────

def _reset_cache():
    """Clear the module-level cache so tests don't bleed into each other."""
    import terminal_hub.display as _mod
    _mod._CACHE = None


# ── happy path ────────────────────────────────────────────────────────────────

def test_display_happy_path():
    from terminal_hub.display import display
    result = display("gh_plan.bootstrap_ready", issue_count=5, milestone_count=2)
    assert result == "✅ **gh-plan ready** — 5 issues, 2 milestones"


def test_display_no_kwargs_no_placeholders():
    from terminal_hub.display import display
    result = display("gh_plan.no_open_issues")
    assert result == "No open issues."


def test_display_project_root_set():
    from terminal_hub.display import display
    result = display("project_root.set", path="/some/path")
    assert result == "📁 **Project root:** /some/path"


def test_display_sync_issues_synced():
    from terminal_hub.display import display
    result = display(
        "sync.issues_synced",
        updated=3, repo="owner/repo", state="open",
        skipped=1, closed_locally=0, checked=4,
    )
    assert "✓ Synced 3 issue(s)" in result
    assert "owner/repo" in result
    assert "Skipped 1 unchanged" in result
    assert "Closed locally: 0" in result


def test_display_newlines_in_synced_template():
    from terminal_hub.display import display
    result = display(
        "sync.issues_synced",
        updated=1, repo="r/r", state="open",
        skipped=0, closed_locally=0, checked=1,
    )
    assert "\n" in result


def test_display_issue_hooked():
    from terminal_hub.display import display
    result = display("gh_implementation.issue_hooked", slug="42", title="My Issue")
    assert "Hooked" in result
    assert "#42" in result
    assert "My Issue" in result


def test_display_issue_unhooked_no_suffix():
    from terminal_hub.display import display
    result = display("gh_implementation.issue_unhooked", slug="42", suffix="")
    assert "Unhooked" in result
    assert "#42" in result
    assert "file deleted" not in result


def test_display_issue_unhooked_with_suffix():
    from terminal_hub.display import display
    result = display("gh_implementation.issue_unhooked", slug="42", suffix=", file deleted")
    assert "file deleted" in result


def test_display_context_loaded_base():
    from terminal_hub.display import display
    result = display("gh_implementation.context_loaded", issue_slug="7", details="")
    assert "Context loaded" in result
    assert "#7" in result


def test_display_context_detail_design():
    from terminal_hub.display import display
    result = display("gh_implementation.context_detail_design", design_count=3)
    assert "3 design sections" in result


def test_display_context_detail_docs():
    from terminal_hub.display import display
    result = display("gh_implementation.context_detail_docs", docs_count=2)
    assert "2 connected docs" in result


def test_display_prompt_coloring_question_line():
    from terminal_hub.display import display
    result = display("prompt_coloring.question_line", icon="❓", wrap="**", question="Hello?")
    assert result == "❓ **Hello?**"


def test_display_prompt_coloring_question_with_options():
    from terminal_hub.display import display
    result = display(
        "prompt_coloring.question_with_options",
        icon="❓", wrap="**", question="Do it?", opts_str="yes / no",
    )
    assert result == "❓ **Do it?** *(yes / no)*"


# ── error cases ───────────────────────────────────────────────────────────────

def test_display_missing_feature_raises_key_error():
    from terminal_hub.display import display
    with pytest.raises(KeyError, match="nonexistent"):
        display("nonexistent.action")


def test_display_missing_action_raises_key_error():
    from terminal_hub.display import display
    with pytest.raises(KeyError, match="no_such_action"):
        display("gh_plan.no_such_action")


def test_display_invalid_key_format_raises_key_error():
    from terminal_hub.display import display
    with pytest.raises(KeyError, match="feature.action"):
        display("nodot")


def test_display_missing_variable_raises_key_error():
    from terminal_hub.display import display
    with pytest.raises(KeyError):
        display("gh_plan.bootstrap_ready")  # missing issue_count and milestone_count


def test_display_missing_one_variable_raises_key_error():
    from terminal_hub.display import display
    with pytest.raises(KeyError):
        display("gh_plan.bootstrap_ready", issue_count=5)  # missing milestone_count


# ── caching ───────────────────────────────────────────────────────────────────

def test_display_caches_json_after_first_call():
    _reset_cache()
    import terminal_hub.display as mod
    from terminal_hub.display import display

    assert mod._CACHE is None
    display("gh_plan.no_open_issues")
    assert mod._CACHE is not None
    cache_id = id(mod._CACHE)

    # Second call must reuse the same dict object
    display("gh_plan.no_open_issues")
    assert id(mod._CACHE) == cache_id


def test_display_reads_from_real_json_file():
    """Ensure the JSON file exists and is parseable."""
    from pathlib import Path
    json_path = Path(__file__).parent.parent / "terminal_hub" / "predefined_text.json"
    assert json_path.exists(), "predefined_text.json must exist"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "gh_plan" in data
    assert "sync" in data
    assert "gh_implementation" in data
    assert "project_root" in data
    assert "prompt_coloring" in data


# ── load_data ─────────────────────────────────────────────────────────────────

def test_load_data_returns_raw_value():
    from terminal_hub.display import load_data
    # gh_plan.no_open_issues is a string — load_data should return it as-is
    val = load_data("gh_plan.no_open_issues")
    assert isinstance(val, str)
    assert val == "No open issues."


def test_load_data_missing_feature_raises_key_error():
    from terminal_hub.display import load_data
    with pytest.raises(KeyError):
        load_data("missing.action")


def test_load_data_invalid_key_format_raises_key_error():
    from terminal_hub.display import load_data
    with pytest.raises(KeyError, match="feature.action"):
        load_data("nodot")


def test_load_data_missing_action_raises_key_error():
    from terminal_hub.display import load_data
    with pytest.raises(KeyError, match="no_such_action"):
        load_data("gh_plan.no_such_action")


def test_display_non_string_raises_key_error():
    """display() on a non-string JSON value (e.g. a dict) raises KeyError."""
    _reset_cache()
    import terminal_hub.display as mod
    fake_data = {"test_feature": {"my_dict": {"key": "val"}}}
    with patch.object(mod, "_CACHE", fake_data):
        from terminal_hub.display import display
        with pytest.raises(KeyError, match="not a string template"):
            display("test_feature.my_dict")
