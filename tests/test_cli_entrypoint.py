"""Tests for the terminal-hub CLI entry point."""
import subprocess
import sys

import pytest


def run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "terminal_hub", *args],
        capture_output=True,
        text=True,
    )


# ── --help ────────────────────────────────────────────────────────────────────
# One interpreter spawn, four assertions about its output. These four tests
# previously ran `run("--help")` each, paying four subprocess launches to
# inspect one string.

@pytest.fixture(scope="module")
def help_output() -> subprocess.CompletedProcess:
    return run("--help")


def test_help_exits_zero(help_output):
    assert help_output.returncode == 0


def test_help_shows_install_subcommand(help_output):
    assert "install" in help_output.stdout


def test_help_shows_verify_subcommand(help_output):
    assert "verify" in help_output.stdout


def test_help_shows_description(help_output):
    assert "terminal-hub" in help_output.stdout.lower() or "github" in help_output.stdout.lower()


# ── subcommand help ───────────────────────────────────────────────────────────

def test_install_help_exits_zero():
    result = run("install", "--help")
    assert result.returncode == 0


def test_verify_help_exits_zero():
    result = run("verify", "--help")
    assert result.returncode == 0


# ── verify with no install ────────────────────────────────────────────────────

def test_verify_exits_nonzero_when_not_installed(tmp_path):
    """verify should exit 1 when terminal-hub is not in ~/.claude.json."""
    fake_claude_json = tmp_path / ".claude.json"
    fake_claude_json.write_text('{"mcpServers": {}}')

    result = subprocess.run(
        [sys.executable, "-c",
         f"from terminal_hub.cli.install import run_verify; from pathlib import Path; run_verify(Path('{fake_claude_json}'))"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "NOT" in result.stdout or "not" in result.stdout.lower()


def test_verify_exits_zero_when_installed(tmp_path):
    """verify should exit 0 when terminal-hub entry exists."""
    import json
    fake_claude_json = tmp_path / ".claude.json"
    fake_claude_json.write_text(json.dumps({
        "mcpServers": {
            "terminal-hub": {"command": "python3", "args": ["-m", "terminal_hub"]}
        }
    }))

    result = subprocess.run(
        [sys.executable, "-c",
         f"from terminal_hub.cli.install import run_verify; from pathlib import Path; run_verify(Path('{fake_claude_json}'))"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "✓" in result.stdout
