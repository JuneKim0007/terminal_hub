"""Tests for ### Available for Reuse section generation and preservation (#163)."""
from __future__ import annotations

import pytest

from extensions.github_planner import _format_reuse_block, _preserve_reuse_block


# ── _format_reuse_block ───────────────────────────────────────────────────────


def test_format_reuse_block_with_string_exports():
    """file_index entry with plain string exports → produces Available for Reuse lines."""
    files = [
        {
            "path": "extensions/foo/bar.py",
            "exports": ["my_func", "MyClass"],
            "module_doc": "Does something useful.",
        }
    ]
    result = _format_reuse_block(files)
    assert result.startswith("### Available for Reuse\n")
    assert "- `my_func` — `extensions/foo/bar.py` — Does something useful." in result
    assert "- `MyClass` — `extensions/foo/bar.py` — Does something useful." in result


def test_format_reuse_block_with_dict_exports():
    """file_index entry with dict exports → uses signature and doc fields."""
    files = [
        {
            "path": "lib/utils.py",
            "exports": [
                {"name": "helper", "signature": "helper(x, y)", "doc": "Returns sum of x and y."},
            ],
            "module_doc": "",
        }
    ]
    result = _format_reuse_block(files)
    assert "- `helper(x, y)` — `lib/utils.py` — Returns sum of x and y." in result


def test_format_reuse_block_empty_exports():
    """No exports → returns empty string, no block emitted."""
    files = [
        {"path": "some/file.py", "exports": [], "module_doc": "Something."},
        {"path": "other/file.py", "module_doc": "No exports key at all."},
    ]
    result = _format_reuse_block(files)
    assert result == ""


def test_format_reuse_block_empty_list():
    """Empty file list → returns empty string."""
    assert _format_reuse_block([]) == ""


def test_format_reuse_block_caps_at_20():
    """More than 20 exports → output capped at 20 lines."""
    exports = [f"func_{i}" for i in range(30)]
    files = [{"path": "big.py", "exports": exports, "module_doc": "Module doc."}]
    result = _format_reuse_block(files)
    lines = [ln for ln in result.splitlines() if ln.startswith("- ")]
    assert len(lines) == 20


def test_format_reuse_block_no_module_doc_uses_dash():
    """Export with no module_doc → uses — as description."""
    files = [{"path": "x.py", "exports": ["do_thing"], "module_doc": ""}]
    result = _format_reuse_block(files)
    assert "— —" in result


# ── _preserve_reuse_block ─────────────────────────────────────────────────────


def test_preserve_reuse_block_injected_when_missing():
    """Existing section has Available for Reuse; new content lacks it → merged result contains it."""
    existing = (
        "## Feature\n\n"
        "### Existing Design\n- some design\n\n"
        "### Available for Reuse\n- `foo()` — `bar.py` — does foo\n\n"
        "### Extension Guidelines\n- follow patterns\n"
    )
    new_content = (
        "## Feature\n\n"
        "### Existing Design\n- updated design\n\n"
        "### Extension Guidelines\n- follow new patterns\n"
    )
    result = _preserve_reuse_block(existing, new_content)
    assert "### Available for Reuse" in result
    assert "- `foo()` — `bar.py` — does foo" in result
    # Should appear before Extension Guidelines
    reuse_pos = result.index("### Available for Reuse")
    ext_pos = result.index("### Extension Guidelines")
    assert reuse_pos < ext_pos


def test_preserve_reuse_block_not_duplicated():
    """New content already has Available for Reuse → existing block not re-injected."""
    existing = (
        "## Feature\n\n"
        "### Available for Reuse\n- `old()` — `old.py` — old description\n\n"
        "### Extension Guidelines\n- old guidelines\n"
    )
    new_content = (
        "## Feature\n\n"
        "### Available for Reuse\n- `new()` — `new.py` — new description\n\n"
        "### Extension Guidelines\n- new guidelines\n"
    )
    result = _preserve_reuse_block(existing, new_content)
    # New content returned unchanged; old block not injected
    assert result == new_content
    assert result.count("### Available for Reuse") == 1
    assert "- `old()` — `old.py`" not in result
    assert "- `new()` — `new.py`" in result


def test_preserve_reuse_block_no_existing_block():
    """Existing section lacks Available for Reuse → new section returned unchanged."""
    existing = (
        "## Feature\n\n"
        "### Existing Design\n- design\n\n"
        "### Extension Guidelines\n- guidelines\n"
    )
    new_content = (
        "## Feature\n\n"
        "### Existing Design\n- updated design\n\n"
        "### Extension Guidelines\n- new guidelines\n"
    )
    result = _preserve_reuse_block(existing, new_content)
    assert result == new_content
    assert "### Available for Reuse" not in result


def test_preserve_reuse_block_appended_when_no_extension_guidelines():
    """Existing has Available for Reuse; new lacks both it and Extension Guidelines → appended at end."""
    existing = (
        "## Feature\n\n"
        "### Available for Reuse\n- `util()` — `u.py` — utility\n"
    )
    new_content = "## Feature\n\n### Existing Design\n- design\n"
    result = _preserve_reuse_block(existing, new_content)
    assert "### Available for Reuse" in result
    assert "- `util()` — `u.py` — utility" in result
