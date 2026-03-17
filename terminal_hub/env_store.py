"""Read/write hub_agents/.env for per-project credential and path storage."""
from pathlib import Path


def read_env(root: Path) -> dict[str, str]:
    """Parse hub_agents/.env. Returns empty dict if file missing."""
    path = root / "hub_agents" / ".env"
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def write_env(root: Path, values: dict[str, str]) -> None:
    """Merge values into hub_agents/.env and ensure hub_agents/ is gitignored."""
    path = root / "hub_agents" / ".env"
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = read_env(root)
    existing.update({k: v for k, v in values.items() if v})

    lines = [f"{k}={v}" for k, v in existing.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _ensure_gitignored(root)


def _ensure_gitignored(root: Path) -> None:
    """Add hub_agents/ to .gitignore if not already present."""
    entry = "hub_agents/"
    gitignore = root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if entry in content:
            return
        gitignore.write_text(content.rstrip() + f"\n{entry}\n", encoding="utf-8")
    else:
        gitignore.write_text(f"{entry}\n", encoding="utf-8")
