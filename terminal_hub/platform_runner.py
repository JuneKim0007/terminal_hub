"""OS detection and subprocess runner for terminal-hub extensions."""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any


# ── OS Detection ──────────────────────────────────────────────────────────────

def detect_distro() -> str:
    """Detect Linux distro from /etc/alpine-release or /etc/os-release.

    Returns one of: ubuntu | fedora | arch | alpine | linux (generic fallback).
    """
    # Alpine ships /etc/alpine-release even without os-release
    if Path("/etc/alpine-release").exists():
        return "alpine"

    for path in ["/etc/os-release", "/usr/lib/os-release"]:
        try:
            text = Path(path).read_text(encoding="utf-8").lower()
            if "ubuntu" in text or "debian" in text:
                return "ubuntu"
            if "fedora" in text or "rhel" in text or "centos" in text:
                return "fedora"
            if "arch" in text:
                return "arch"
            if "alpine" in text:
                return "alpine"
        except OSError:
            continue

    return "linux"


def detect_platform() -> str:
    """Return platform key: darwin | ubuntu | fedora | arch | alpine | windows | linux."""
    system = platform.system().lower()
    if system == "darwin":
        return "darwin"
    if system == "windows":
        return "windows"
    return detect_distro()


# ── Command Runner ─────────────────────────────────────────────────────────────

def run_extension(ext: dict[str, Any], platform_key: str | None = None) -> dict[str, Any]:
    """Run an extension's commands for the detected platform.

    Resolution order: exact platform match → 'linux' generic fallback → error.

    Returns dict with keys: success, _display, and on failure: error, cmd, fallback.
    """
    if platform_key is None:
        platform_key = detect_platform()

    platforms = ext.get("platforms", {})
    commands = platforms.get(platform_key) or platforms.get("linux")

    if not commands:
        msg = f"No commands defined for platform '{platform_key}' or 'linux'"
        return {
            "success": False,
            "error": msg,
            "fallback": ext.get("fallback", "claude"),
            "_display": f"⚠ Extension '{ext.get('id')}' skipped: {msg}",
        }

    for cmd in commands:
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip()
                return {
                    "success": False,
                    "error": err,
                    "cmd": cmd,
                    "fallback": ext.get("fallback", "claude"),
                    "_display": f"✗ {ext.get('id')} failed: {err}",
                }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"timed out after 30s: {cmd}",
                "cmd": cmd,
                "fallback": ext.get("fallback", "claude"),
                "_display": f"✗ {ext.get('id')} timed out",
            }

    return {
        "success": True,
        "_display": f"✓ {ext.get('id')} completed",
    }
