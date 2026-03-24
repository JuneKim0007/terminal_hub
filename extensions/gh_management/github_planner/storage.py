"""Read/write issue .md files and project context documents with YAML front matter."""
import os
import re
import tempfile
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

_GH_PLANNER_DOCS = "hub_agents/extensions/gh_planner"

# Legacy flat paths — kept only for migration; new writes go to _GH_PLANNER_DOCS
_DOC_FILES_LEGACY = {
    "project_description": "hub_agents/project_description.md",
    "architecture": "hub_agents/architecture_design.md",
}

# Namespaced paths for new writes
_DOC_FILES = {
    "project_description": f"{_GH_PLANNER_DOCS}/project_summary.md",
    "architecture": f"{_GH_PLANNER_DOCS}/project_detail.md",
}

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,59}$")


class IssueStatus(str, Enum):
    """Valid status values for issue files. Subclasses str so YAML serialises as plain strings."""

    PENDING = "pending"
    OPEN    = "open"
    CLOSED  = "closed"

    def __str__(self) -> str:
        return self.value


# Keep module-level aliases for backwards compat within the codebase
STATUS_PENDING = IssueStatus.PENDING
STATUS_OPEN    = IssueStatus.OPEN
STATUS_CLOSED  = IssueStatus.CLOSED


def validate_slug(slug: str) -> None:
    """Raise ValueError if *slug* looks like a path traversal or is structurally invalid."""
    if not _SLUG_RE.fullmatch(slug):
        raise ValueError(f"Invalid slug {slug!r}: must match [a-z0-9][a-z0-9-]{{0,59}}")


def _issues_dir(root: Path) -> Path:
    return root / "hub_agents" / "issues"


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically using a temp file + os.replace."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def resolve_slug(root: Path, base_slug: str) -> str:
    """Return a unique slug, appending -2, -3, etc. on filesystem collision."""
    issues = _issues_dir(root)
    slug = base_slug
    counter = 2
    while (issues / f"{slug}.md").exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def next_local_number(root: Path) -> str:
    """Return the next sequential local issue number as a string (e.g. '1', '2', '3').

    Scans hub_agents/issues/ for purely numeric stems (e.g. '1.md', '42.md') and
    returns max + 1. Text-slugged files from earlier versions or GitHub syncs are ignored.
    Starts at '1' when no numeric issues exist yet.
    """
    issues_dir = _issues_dir(root)
    max_num = 0
    if issues_dir.exists():
        for path in issues_dir.glob("*.md"):
            if path.stem.isdigit():
                max_num = max(max_num, int(path.stem))
    return str(max_num + 1)


_AGENT_WORKFLOW_NOTE = (
    "> **Agent workflow** — step-by-step guide for how an agent should resolve this issue. "
    "Follow these steps in order."
)


def write_issue_file(
    root: Path,
    slug: str,
    title: str,
    body: str,
    assignees: list[str],
    labels: list[str],
    created_at: date,
    status: IssueStatus | str = IssueStatus.PENDING,
    issue_number: int | None = None,
    github_url: str | None = None,
    workflow: list[str] | None = None,
    agent_workflow: list[str] | None = None,
    note: str | None = None,
    milestone_number: int | None = None,
    milestone_title: str | None = None,
    design_refs: list[str] | None = None,
    updated_at: str | None = None,
) -> Path:
    """Write an issue .md file with YAML front matter atomically. Returns the file path.

    agent_workflow: ordered steps for how an agent should resolve this issue.
      Stored in YAML frontmatter and rendered as a ## Agent Workflow body section.
      Example: ["Scan all files and cache project structure",
                "Build knowledge base separating relevant vs unrelated files",
                "Implement the fix", "Write tests", "Verify suite passes"]
    """
    validate_slug(slug)
    path = _issues_dir(root) / f"{slug}.md"
    frontmatter: dict[str, Any] = {
        "title": title,
        "status": str(status),
        "created_at": created_at.strftime("%Y-%m-%d"),
        "assignees": assignees,
        "labels": labels,
        "workflow": workflow if workflow is not None else [],
        "agent_workflow": agent_workflow,
        "note": note,
        "milestone_number": milestone_number,
        "milestone_title": milestone_title,
    }
    if issue_number is not None:
        frontmatter["issue_number"] = issue_number
    if github_url is not None:
        frontmatter["github_url"] = github_url
    if design_refs:
        frontmatter["design_refs"] = design_refs
    if updated_at is not None:
        frontmatter["updated_at"] = updated_at

    # Prefix body with issue identifier header for easy agent orientation
    header = f"# Issue #{slug}: {title}\n\n"

    # Append Agent Workflow section when steps are provided
    workflow_section = ""
    if agent_workflow:
        steps = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(agent_workflow))
        workflow_section = f"\n\n---\n\n## Agent Workflow\n\n{_AGENT_WORKFLOW_NOTE}\n\n{steps}"

    content = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{header}{body}{workflow_section}\n"
    _atomic_write(path, content)
    return path


def update_issue_status(
    root: Path,
    slug: str,
    status: IssueStatus | str,
    issue_number: int | None = None,
    github_url: str | None = None,
) -> Path | None:
    """Update status (and optionally issue_number/github_url) on an existing issue file.

    Returns the path on success, None if the file doesn't exist.
    Writes atomically to prevent partial-write data loss.
    """
    validate_slug(slug)
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    fm: dict[str, Any] = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n") if len(parts) > 2 else ""

    fm["status"] = str(status)
    if issue_number is not None:
        fm["issue_number"] = issue_number
    if github_url is not None:
        fm["github_url"] = github_url

    _atomic_write(path, f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{body}")
    return path


def read_issue_frontmatter(root: Path, slug: str) -> dict[str, Any] | None:
    """Parse YAML front matter from an issue file. Returns None if file missing or malformed."""
    validate_slug(slug)
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    try:
        return yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None


def read_issue_file(root: Path, slug: str) -> str | None:
    """Return full file content or None if not found."""
    validate_slug(slug)
    path = _issues_dir(root) / f"{slug}.md"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def list_issue_files(root: Path) -> list[dict[str, Any]]:
    """Return metadata for all issue files, sorted by created_at descending."""
    issues_dir = _issues_dir(root)
    if not issues_dir.exists():
        return []
    results = []
    for md_file in issues_dir.glob("*.md"):
        slug = md_file.stem
        try:
            validate_slug(slug)
        except ValueError:
            continue  # skip files with non-slug names
        fm = read_issue_frontmatter(root, slug)
        if fm:
            entry: dict[str, Any] = {
                "slug": slug,
                "title": fm.get("title", ""),
                "status": fm.get("status", str(IssueStatus.PENDING)),
                "issue_number": fm.get("issue_number"),
                "github_url": fm.get("github_url"),
                "created_at": fm.get("created_at"),
                "updated_at": fm.get("updated_at"),
                "assignees": fm.get("assignees", []),
                "labels": fm.get("labels", []),
                "file": f"hub_agents/issues/{slug}.md",
            }
            if fm.get("design_refs"):
                entry["design_refs"] = fm["design_refs"]
            results.append(entry)
    return sorted(results, key=lambda x: x["created_at"] or "", reverse=True)


def write_doc_file(root: Path, doc_key: str, content: str) -> Path:
    """Overwrite a project context doc. doc_key must be 'project_description' or 'architecture'."""
    if doc_key not in _DOC_FILES:
        raise ValueError(f"Unknown doc_key {doc_key!r}. Valid keys: {list(_DOC_FILES)}")
    path = root / _DOC_FILES[doc_key]
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, content)
    return path


def read_doc_file(root: Path, doc_key: str) -> str | None:
    """Return content of a project context doc or None if it doesn't exist.

    Reads from the namespaced path first; falls back to legacy flat path and
    migrates the file on first access.
    """
    if doc_key not in _DOC_FILES:
        raise ValueError(f"Unknown doc_key {doc_key!r}. Valid keys: {list(_DOC_FILES)}")
    new_path = root / _DOC_FILES[doc_key]
    if new_path.exists():
        try:
            return new_path.read_text(encoding="utf-8")
        except OSError:
            return None
    # Migration: check legacy flat path
    legacy_path = root / _DOC_FILES_LEGACY[doc_key]
    if legacy_path.exists():
        try:
            content = legacy_path.read_text(encoding="utf-8")
            # Migrate to new location
            new_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(new_path, content)
            legacy_path.unlink(missing_ok=True)
            return content
        except OSError:
            pass
    return None
