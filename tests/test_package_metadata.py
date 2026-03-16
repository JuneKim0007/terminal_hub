"""Tests for package metadata and distribution structure."""
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


# ── Python package ────────────────────────────────────────────────────────────

def test_package_importable():
    import terminal_hub
    assert terminal_hub is not None


def test_version_accessible():
    import terminal_hub
    assert hasattr(terminal_hub, "__version__")
    assert isinstance(terminal_hub.__version__, str)
    assert terminal_hub.__version__  # non-empty


def test_version_format():
    import terminal_hub
    parts = terminal_hub.__version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


# ── pyproject.toml ────────────────────────────────────────────────────────────

def test_pyproject_exists():
    assert (ROOT / "pyproject.toml").exists()


def test_pyproject_has_entrypoint():
    import tomllib
    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    scripts = data["project"]["scripts"]
    assert "terminal-hub" in scripts
    assert scripts["terminal-hub"] == "terminal_hub.__main__:main"


def test_pyproject_requires_python_310():
    import tomllib
    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    assert "3.10" in data["project"]["requires-python"]


def test_pyproject_has_required_deps():
    import tomllib
    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    deps = " ".join(data["project"]["dependencies"])
    assert "mcp" in deps
    assert "httpx" in deps
    assert "pyyaml" in deps


# ── Plugin manifests ──────────────────────────────────────────────────────────

def test_plugin_json_exists():
    assert (ROOT / ".claude-plugin" / "plugin.json").exists()


def test_marketplace_json_exists():
    assert (ROOT / ".claude-plugin" / "marketplace.json").exists()


def test_install_modules_json_exists():
    assert (ROOT / ".claude-plugin" / "install-modules.json").exists()


def test_plugin_json_has_required_fields():
    data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    for field in ("name", "version", "description", "repository"):
        assert field in data, f"Missing field: {field}"


def test_marketplace_json_declares_plugin():
    data = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert "plugins" in data
    assert len(data["plugins"]) >= 1
    assert data["plugins"][0]["name"] == "terminal-hub"


def test_install_modules_declares_agents_and_hooks():
    data = json.loads((ROOT / ".claude-plugin" / "install-modules.json").read_text())
    kinds = {m["kind"] for m in data["modules"]}
    assert "agents" in kinds
    assert "hooks" in kinds


def test_plugin_name_matches_package_name():
    import tomllib
    with open(ROOT / "pyproject.toml", "rb") as f:
        pyproject = tomllib.load(f)
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert pyproject["project"]["name"] == plugin["name"]
