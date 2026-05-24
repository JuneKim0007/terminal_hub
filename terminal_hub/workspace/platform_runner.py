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


# ── Agent Escalation ───────────────────────────────────────────────────────────

def escalate_to_agent(result: dict[str, Any], context: str = "") -> dict[str, Any]:
    """Wrap a failed extension result with agent escalation guidance.

    When a Python-layer operation fails, this surfaces a _guidance hint so
    Claude handles the operation conversationally instead of silently failing.

    Args:
        result: The failed result dict from run_extension (must have success=False).
        context: Optional human-readable description of what was being attempted.

    Returns:
        The result dict augmented with _agent_escalation and _guidance fields.
    """
    if result.get("success"):
        return result  # no escalation needed for success

    ext_id = result.get("id", "extension")
    error = result.get("error", "unknown error")
    failed_cmd = result.get("cmd", "")

    parts = [f"The Python layer could not complete '{ext_id}'."]
    if failed_cmd:
        parts.append(f"Failed command: `{failed_cmd}`")
    if error:
        parts.append(f"Reason: {error}")
    if context:
        parts.append(f"Context: {context}")
    parts.append(
        "Please handle this operation conversationally: "
        "ask the user what they need, then use the appropriate tools or commands directly."
    )

    return {
        **result,
        "_agent_escalation": True,
        "_guidance": "terminal-hub://escalation/handle-conversationally",
        "_escalation_message": " ".join(parts),
    }


# ── Command Runner ─────────────────────────────────────────────────────────────

def run_extension(ext: dict[str, Any], platform_key: str | None = None) -> dict[str, Any]:
    """Run an extension's commands for the detected platform.

    Resolution order: exact platform match → 'linux' generic fallback → error.

    On failure, automatically calls escalate_to_agent() so callers receive
    actionable guidance for handing off to Claude conversationally.

    Returns dict with keys: success, _display, and on failure: error, cmd,
    fallback, _agent_escalation, _guidance, _escalation_message.
    """
    if platform_key is None:
        platform_key = detect_platform()

    platforms = ext.get("platforms", {})
    commands = platforms.get(platform_key) or platforms.get("linux")

    if not commands:
        msg = f"No commands defined for platform '{platform_key}' or 'linux'"
        failed = {
            "success": False,
            "id": ext.get("id"),
            "error": msg,
            "fallback": ext.get("fallback", "claude"),
            "_display": f"⚠ Extension '{ext.get('id')}' skipped: {msg}",
        }
        return escalate_to_agent(failed)

    for cmd in commands:
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip()
                failed = {
                    "success": False,
                    "id": ext.get("id"),
                    "error": err,
                    "cmd": cmd,
                    "fallback": ext.get("fallback", "claude"),
                    "_display": f"✗ {ext.get('id')} failed: {err}",
                }
                return escalate_to_agent(failed)
        except subprocess.TimeoutExpired:
            failed = {
                "success": False,
                "id": ext.get("id"),
                "error": f"timed out after 30s: {cmd}",
                "cmd": cmd,
                "fallback": ext.get("fallback", "claude"),
                "_display": f"✗ {ext.get('id')} timed out",
            }
            return escalate_to_agent(failed)

    return {
        "success": True,
        "_display": f"✓ {ext.get('id')} completed",
    }
