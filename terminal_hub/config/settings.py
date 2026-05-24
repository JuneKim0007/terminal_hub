"""Read/write .terminal_hub/config.yaml and workspace mode detection."""
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class WorkspaceMode(StrEnum):
    LOCAL = "local"
    GITHUB = "github"


_CONFIG_FILE = "hub_agents/config.yaml"


def load_config(root: Path) -> dict[str, Any] | None:
    """Return config dict or None if config file does not exist."""
    path = root / _CONFIG_FILE
    if not path.exists():
        return None
    with path.open() as f:
        return yaml.safe_load(f)


def save_config(root: Path, mode: WorkspaceMode, repo: str | None) -> None:
    """Write config to .terminal_hub/config.yaml."""
    path = root / _CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_config(root) or {}
    existing["mode"] = str(mode)
    existing["repo"] = repo
    with path.open("w") as f:
        yaml.dump(existing, f)


def read_preference(root: Path, key: str, default: Any = None) -> Any:
    """Return a value from config.yaml preferences dict, or default if absent."""
    cfg = load_config(root) or {}
    return cfg.get("preferences", {}).get(key, default)


def write_preference(root: Path, key: str, value: Any) -> None:
    """Persist a single preference key in config.yaml under the 'preferences' dict."""
    path = root / _CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = load_config(root) or {}
    prefs = cfg.get("preferences", {})
    prefs[key] = value
    cfg["preferences"] = prefs
    with path.open("w") as f:
        yaml.dump(cfg, f)
