"""Tests for terminal_hub.platform_runner."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from terminal_hub.platform_runner import detect_distro, detect_platform, run_extension


# ── detect_platform ────────────────────────────────────────────────────────────

def test_detect_platform_darwin():
    with patch("platform.system", return_value="Darwin"):
        assert detect_platform() == "darwin"


def test_detect_platform_windows():
    with patch("platform.system", return_value="Windows"):
        assert detect_platform() == "windows"


def test_detect_platform_linux_calls_detect_distro():
    with patch("platform.system", return_value="Linux"):
        with patch("terminal_hub.platform_runner.detect_distro", return_value="ubuntu") as mock_dd:
            result = detect_platform()
            mock_dd.assert_called_once()
            assert result == "ubuntu"


# ── detect_distro ──────────────────────────────────────────────────────────────

def test_detect_distro_alpine_release_file(tmp_path, monkeypatch):
    """Returns 'alpine' when /etc/alpine-release exists."""
    alpine_release = tmp_path / "alpine-release"
    alpine_release.write_text("3.18.0\n")

    original_path_class = Path

    class PatchedPath(type(original_path_class())):
        def __new__(cls, *args, **kwargs):
            instance = original_path_class.__new__(cls, *args, **kwargs)
            return instance

    # Patch Path.exists so /etc/alpine-release returns True
    original_exists = Path.exists

    def patched_exists(self):
        if str(self) == "/etc/alpine-release":
            return True
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", patched_exists)
    assert detect_distro() == "alpine"


def test_detect_distro_ubuntu(tmp_path, monkeypatch):
    """Returns 'ubuntu' when /etc/os-release contains 'ubuntu'."""
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=ubuntu\nNAME="Ubuntu 22.04"\n')

    original_exists = Path.exists
    original_read_text = Path.read_text

    def patched_exists(self):
        if str(self) == "/etc/alpine-release":
            return False
        return original_exists(self)

    def patched_read_text(self, *args, **kwargs):
        if str(self) == "/etc/os-release":
            return os_release.read_text()
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", patched_exists)
    monkeypatch.setattr(Path, "read_text", patched_read_text)
    assert detect_distro() == "ubuntu"


def test_detect_distro_fedora(tmp_path, monkeypatch):
    """Returns 'fedora' when /etc/os-release contains 'fedora'."""
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=fedora\nNAME="Fedora Linux 38"\n')

    original_exists = Path.exists
    original_read_text = Path.read_text

    def patched_exists(self):
        if str(self) == "/etc/alpine-release":
            return False
        return original_exists(self)

    def patched_read_text(self, *args, **kwargs):
        if str(self) == "/etc/os-release":
            return os_release.read_text()
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", patched_exists)
    monkeypatch.setattr(Path, "read_text", patched_read_text)
    assert detect_distro() == "fedora"


def test_detect_distro_arch(tmp_path, monkeypatch):
    """Returns 'arch' when /etc/os-release contains 'arch'."""
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=arch\nNAME="Arch Linux"\n')

    original_exists = Path.exists
    original_read_text = Path.read_text

    def patched_exists(self):
        if str(self) == "/etc/alpine-release":
            return False
        return original_exists(self)

    def patched_read_text(self, *args, **kwargs):
        if str(self) == "/etc/os-release":
            return os_release.read_text()
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", patched_exists)
    monkeypatch.setattr(Path, "read_text", patched_read_text)
    assert detect_distro() == "arch"


def test_detect_distro_linux_fallback(monkeypatch):
    """Returns 'linux' when no os-release files are found (OSError raised)."""
    original_exists = Path.exists

    def patched_exists(self):
        if str(self) == "/etc/alpine-release":
            return False
        return original_exists(self)

    def patched_read_text(self, *args, **kwargs):
        if str(self) in ("/etc/os-release", "/usr/lib/os-release"):
            raise OSError("No such file")
        return Path.read_text.__wrapped__(self, *args, **kwargs) if hasattr(Path.read_text, "__wrapped__") else open(str(self)).read()

    monkeypatch.setattr(Path, "exists", patched_exists)
    monkeypatch.setattr(Path, "read_text", patched_read_text)
    assert detect_distro() == "linux"


# ── run_extension ──────────────────────────────────────────────────────────────

def test_run_extension_success():
    """Returns success when command exits 0."""
    ext = {
        "id": "my-ext",
        "platforms": {"darwin": ["true"]},
    }
    result = run_extension(ext, platform_key="darwin")
    assert result["success"] is True
    assert "my-ext" in result["_display"]


def test_run_extension_failure_nonzero():
    """Returns failure with error when command exits non-zero."""
    ext = {
        "id": "my-ext",
        "fallback": "claude",
        "platforms": {"darwin": ["false"]},
    }
    result = run_extension(ext, platform_key="darwin")
    assert result["success"] is False
    assert result["cmd"] == "false"
    assert result["fallback"] == "claude"


def test_run_extension_timeout():
    """Returns failure on timeout."""
    ext = {
        "id": "slow-ext",
        "fallback": "claude",
        "platforms": {"linux": ["sleep 100"]},
    }
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="sleep 100", timeout=30)):
        result = run_extension(ext, platform_key="linux")
    assert result["success"] is False
    assert "timed out" in result["error"]
    assert result["fallback"] == "claude"


def test_run_extension_linux_fallback():
    """Falls back to 'linux' key when exact platform key is absent."""
    ext = {
        "id": "cross-ext",
        "platforms": {"linux": ["true"]},
    }
    result = run_extension(ext, platform_key="ubuntu")
    assert result["success"] is True


def test_run_extension_no_platform_no_linux():
    """Returns error when neither the platform key nor 'linux' key is present."""
    ext = {
        "id": "limited-ext",
        "fallback": "claude",
        "platforms": {"darwin": ["true"]},
    }
    result = run_extension(ext, platform_key="windows")
    assert result["success"] is False
    assert "No commands defined" in result["error"]
    assert result["fallback"] == "claude"
