"""Workspace root resolution and per-OS extension execution.

`locator` figures out where the user's project lives (active project
root, PROJECT_ROOT env var, or cwd). `platform_runner` runs shell
extensions defined in `command_config.json` with OS-aware fallbacks.
"""
from terminal_hub.workspace.locator import (
    _ACTIVE_PROJECT_ROOT,
    _cwd,
    detect_repo,
    init_workspace,
    is_valid_project,
    resolve_workspace_root,
    set_active_project_root,
)
from terminal_hub.workspace.platform_runner import (
    detect_distro,
    detect_platform,
    escalate_to_agent,
    run_extension,
)

__all__ = [
    "set_active_project_root",
    "resolve_workspace_root",
    "is_valid_project",
    "init_workspace",
    "detect_repo",
    "detect_distro",
    "detect_platform",
    "escalate_to_agent",
    "run_extension",
    "_cwd",
    "_ACTIVE_PROJECT_ROOT",
]
