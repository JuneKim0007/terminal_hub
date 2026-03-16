"""Read/write .terminal_hub/.env for per-project credential and path storage."""
from pathlib import Path


def read_env(root: Path) -> dict[str, str]:
    """Parse .terminal_hub/.env. Returns empty dict if file missing."""
    path = root / ".terminal_hub" / ".env"
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def write_env(root: Path, values: dict[str, str]) -> None:
    """Merge values into .terminal_hub/.env and ensure it is gitignored."""
    path = root / ".terminal_hub" / ".env"
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = read_env(root)
    existing.update({k: v for k, v in values.items() if v})

    lines = [f"{k}={v}" for k, v in existing.items()]
    path.write_text("\n".join(lines) + "\n")

    _ensure_gitignored(root)


def _ensure_gitignored(root: Path) -> None:
    """Add .terminal_hub/.env to .gitignore if not already present."""
    entry = ".terminal_hub/.env"
    gitignore = root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if entry in content:
            return
        gitignore.write_text(content.rstrip() + f"\n{entry}\n")
    else:
        gitignore.write_text(f"{entry}\n")
