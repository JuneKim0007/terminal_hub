"""Read/write issue .md files and project context documents with YAML front matter."""
from datetime import date
from pathlib import Path
from typing import Any

import yaml

_DOC_FILES = {
    "project_description": "hub_agents/project_description.md",
    "architecture": "hub_agents/architecture_design.md",
}

# Valid issue status values
STATUS_PENDING = "pending"
STATUS_OPEN    = "open"
STATUS_CLOSED  = "closed"


def _issues_dir(root: Path) -> Path:
    return root / "hub_agents" / "issues"


def resolve_slug(root: Path, base_slug: str) -> str:
    """Return a unique slug, appending -2, -3, etc. on filesystem collision."""
    issues = _issues_dir(root)
    slug = base_slug
    counter = 2
    while (issues / f"{slug}.md").exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def write_issue_file(
    root: Path,
    slug: str,
    title: str,
    body: str,
    assignees: list[str],
    labels: list[str],
    created_at: date,
    status: str = STATUS_PENDING,
    issue_number: int | None = None,
    github_url: str | None = None,
) -> Path:
    """Write an issue .md file with YAML front matter. Returns the file path."""
    path = _issues_dir(root) / f"{slug}.md"
    frontmatter: dict[str, Any] = {
        "title": title,
        "status": status,
        "created_at": created_at.strftime("%Y-%m-%d"),
        "assignees": assignees,
        "labels": labels,
    }
    if issue_number is not None:
        frontmatter["issue_number"] = issue_number
    if github_url is not None:
        frontmatter["github_url"] = github_url

    content = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{body}\n"
    path.write_text(content)
    return path


def update_issue_status(
    root: Path,
    slug: str,
    status: str,
    issue_number: int | None = None,
    github_url: str | None = None,
) -> Path | None:
    """Update status (and optionally issue_number/github_url) on an existing issue file.

    Returns the path on success, None if the file doesn't exist.
    """
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return None

    text = path.read_text()
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    fm: dict[str, Any] = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n") if len(parts) > 2 else ""

    fm["status"] = status
    if issue_number is not None:
        fm["issue_number"] = issue_number
    if github_url is not None:
        fm["github_url"] = github_url

    path.write_text(f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{body}")
    return path


def read_issue_frontmatter(root: Path, slug: str) -> dict[str, Any] | None:
    """Parse YAML front matter from an issue file. Returns None if file missing."""
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return None
    text = path.read_text()
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    return yaml.safe_load(parts[1])


def read_issue_file(root: Path, slug: str) -> str | None:
    """Return full file content or None if not found."""
    path = _issues_dir(root) / f"{slug}.md"
    return path.read_text() if path.exists() else None


def list_issue_files(root: Path) -> list[dict[str, Any]]:
    """Return metadata for all issue files, sorted by created_at descending."""
    results = []
    for md_file in _issues_dir(root).glob("*.md"):
        slug = md_file.stem
        fm = read_issue_frontmatter(root, slug)
        if fm:
            results.append({
                "slug": slug,
                "title": fm.get("title", ""),
                "status": fm.get("status", STATUS_PENDING),
                "issue_number": fm.get("issue_number"),
                "github_url": fm.get("github_url"),
                "created_at": fm.get("created_at"),
                "assignees": fm.get("assignees", []),
                "labels": fm.get("labels", []),
                "file": f"hub_agents/issues/{slug}.md",
            })
    return sorted(results, key=lambda x: x["created_at"] or "", reverse=True)


def write_doc_file(root: Path, doc_key: str, content: str) -> Path:
    """Overwrite a project context doc. doc_key: 'project_description' or 'architecture'."""
    path = root / _DOC_FILES[doc_key]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def read_doc_file(root: Path, doc_key: str) -> str | None:
    """Return content of a project context doc or None if it doesn't exist."""
    path = root / _DOC_FILES[doc_key]
    return path.read_text() if path.exists() else None
