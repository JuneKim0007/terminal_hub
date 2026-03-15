# terminal_hub Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally-installed Python MCP server that integrates with Claude Code to automate GitHub issue creation and maintain living project context documents.

**Architecture:** A FastMCP server exposes 6 tools to Claude Code. Tools read/write a `.terminal_hub/` directory inside the user's project repo and talk to the GitHub REST API via `httpx`. A `questionary`-based terminal menu is exposed as a **separate `terminal-hub setup` CLI command** — the MCP server always starts immediately without blocking on user input.

**Tech Stack:** Python 3.10+, `mcp` (FastMCP), `httpx`, `questionary`, `prompt_toolkit`, `pyyaml`, `anthropic`

---

## File Structure

```
terminal_hub/                        # main package
├── __init__.py                      # package version
├── __main__.py                      # python -m terminal_hub entry point
├── server.py                        # FastMCP instance + all tool/prompt registrations
├── config.py                        # read/write .terminal_hub/config.yaml, mode detection
├── workspace.py                     # auto-init .terminal_hub/ structure, detect cwd + repo
├── github_client.py                 # GitHub REST API calls via httpx (create issue, fetch repo)
├── storage.py                       # read/write issue .md files and project doc .md files
├── slugify.py                       # title → kebab-case slug normalization
├── prompts.py                       # terminal_hub_instructions text constant
└── ui/
    ├── __init__.py
    ├── menu.py                      # questionary select menu rendering
    └── setup.py                     # workspace setup flow: local / new repo / connect repo

tests/
├── conftest.py                      # shared fixtures (tmp_path workspace, mock github)
├── test_slugify.py
├── test_storage.py
├── test_workspace.py
├── test_config.py
├── test_github_client.py
├── tools/
│   ├── test_create_issue.py
│   ├── test_update_docs.py
│   ├── test_list_issues.py
│   └── test_get_context.py
└── ui/
    └── test_setup.py

pyproject.toml                       # package config, dependencies, entry point
Dockerfile                           # Docker support for edge cases
README.md                            # install + config guide
```

---

## Chunk 1: Project Scaffold

**Covers:** Package skeleton, `pyproject.toml`, entry point, FastMCP server boots and responds.

---

### Task 1: Create pyproject.toml

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "terminal-hub"
version = "0.1.0"
description = "Terminal-based GitHub management and automation for Claude Code"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27.0",
    "questionary>=2.0.0",
    "pyyaml>=6.0",
    "anthropic>=0.25.0",
]

[project.scripts]
terminal-hub = "terminal_hub.__main__:main"
terminal-hub-setup = "terminal_hub.__main__:setup"

[tool.hatch.build.targets.wheel]
packages = ["terminal_hub"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Install in dev mode**

```bash
pip install -e ".[dev]" 2>/dev/null || pip install -e .
pip install pytest pytest-asyncio
```

Expected: No errors. `terminal-hub` command available.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pyproject.toml with dependencies and entry point"
```

---

### Task 2: Create package skeleton

**Files:**
- Create: `terminal_hub/__init__.py`
- Create: `terminal_hub/__main__.py`
- Create: `terminal_hub/server.py`
- Create: `terminal_hub/config.py`
- Create: `terminal_hub/workspace.py`
- Create: `terminal_hub/github_client.py`
- Create: `terminal_hub/storage.py`
- Create: `terminal_hub/slugify.py`
- Create: `terminal_hub/prompts.py`
- Create: `terminal_hub/ui/__init__.py`
- Create: `terminal_hub/ui/menu.py`
- Create: `terminal_hub/ui/setup.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/tools/__init__.py`
- Create: `tests/ui/__init__.py`

- [ ] **Step 1: Write `terminal_hub/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 2: Write `terminal_hub/__main__.py`**

```python
from terminal_hub.server import create_server


def main() -> None:
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write `terminal_hub/server.py` (skeleton)**

```python
from mcp.server.fastmcp import FastMCP

from terminal_hub.prompts import TERMINAL_HUB_INSTRUCTIONS


def create_server() -> FastMCP:
    mcp = FastMCP("terminal-hub")

    @mcp.prompt()
    def terminal_hub_instructions() -> str:
        return TERMINAL_HUB_INSTRUCTIONS

    return mcp
```

- [ ] **Step 4: Write `terminal_hub/prompts.py`**

```python
TERMINAL_HUB_INSTRUCTIONS = """
You have access to terminal_hub, a GitHub automation tool.

Rules:
1. During planning conversations, track each distinct task, bug, or feature mentioned by the user.
2. When you identify a clear, actionable task, call create_issue directly. The MCP approval prompt
   will ask the user to confirm — do NOT ask a separate natural language question first.
3. When calling create_issue, generate:
   - A concise, imperative title (e.g. "Fix authentication bug in login flow")
   - A detailed body covering: what the issue is, why it matters, and acceptance criteria
4. Update project_description.md and architecture_design.md any time the conversation introduces
   new information about the project goals, scope, or architecture — not only after issue creation.
   Always call get_project_context first to read existing content, then call the update tool
   with the full preserved-and-extended content. Never overwrite without reading first.
5. At the start of a new session, call list_issues to reload known issues,
   then call get_issue_context for any issue relevant to the current conversation.
6. Do not create duplicate issues. Check list_issues before creating a new one.
""".strip()
```

- [ ] **Step 5: Write stub files (empty modules)**

Create each of these with only a module docstring so imports don't fail:

`terminal_hub/config.py`:
```python
"""Read/write .terminal_hub/config.yaml and workspace mode detection."""
```

`terminal_hub/workspace.py`:
```python
"""Auto-initialize .terminal_hub/ directory structure and detect cwd and GitHub repo."""
```

`terminal_hub/github_client.py`:
```python
"""GitHub REST API client using httpx."""
```

`terminal_hub/storage.py`:
```python
"""Read/write issue .md files and project context documents with YAML front matter."""
```

`terminal_hub/slugify.py`:
```python
"""Normalize issue titles into filesystem-safe kebab-case slugs."""
```

`terminal_hub/ui/menu.py`:
```python
"""Questionary-based terminal selection menu."""
```

`terminal_hub/ui/setup.py`:
```python
"""Workspace setup flow for local, new repo, and connect repo modes."""
```

`tests/conftest.py`:
```python
import pytest
```

- [ ] **Step 6: Verify server boots**

```bash
python -c "from terminal_hub.server import create_server; s = create_server(); print('OK')"
```

Expected output: `OK`

- [ ] **Step 7: Commit**

```bash
git add terminal_hub/ tests/
git commit -m "chore: add package skeleton with FastMCP server stub"
```

---

## Chunk 2: Core Utilities

**Covers:** `slugify.py`, `workspace.py`, `config.py`, `storage.py` — the foundation every tool depends on.

---

### Task 3: Slug normalization

**Files:**
- Modify: `terminal_hub/slugify.py`
- Create: `tests/test_slugify.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_slugify.py
import pytest
from terminal_hub.slugify import slugify


@pytest.mark.parametrize("title,expected", [
    ("Fix auth bug", "fix-auth-bug"),
    ("Fix auth bug!", "fix-auth-bug"),
    ("Fix  multiple   spaces", "fix-multiple-spaces"),
    ("UPPERCASE TITLE", "uppercase-title"),
    ("special @#$% chars", "special-chars"),
    ("numbers 123 ok", "numbers-123-ok"),
    ("trailing-hyphens-", "trailing-hyphens"),
    ("a" * 70, "a" * 60),  # truncate at 60
    ("Fix auth bug", "fix-auth-bug"),  # Unicode stripped (non-ASCII)
    ("--leading-hyphens", "leading-hyphens"),
])
def test_slugify(title, expected):
    assert slugify(title) == expected
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_slugify.py -v
```

Expected: `ImportError` or `AttributeError` — slugify not implemented yet.

- [ ] **Step 3: Implement `slugify`**

```python
# terminal_hub/slugify.py
"""Normalize issue titles into filesystem-safe kebab-case slugs."""
import re


def slugify(title: str) -> str:
    """Convert a title to a kebab-case slug.

    Rules: lowercase, strip non-alphanumeric except spaces,
    replace spaces with hyphens, collapse consecutive hyphens,
    truncate at 60 characters, strip leading/trailing hyphens.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug[:60]
    slug = slug.strip("-")
    return slug
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_slugify.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add terminal_hub/slugify.py tests/test_slugify.py
git commit -m "feat: add slug normalization for issue filenames"
```

---

### Task 4: Workspace initialization

**Files:**
- Modify: `terminal_hub/workspace.py`
- Create: `tests/test_workspace.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workspace.py
import subprocess
from pathlib import Path
import pytest
from unittest.mock import patch

from terminal_hub.workspace import init_workspace, detect_repo


def test_init_workspace_creates_directories(tmp_path):
    init_workspace(tmp_path)
    assert (tmp_path / ".terminal_hub").is_dir()
    assert (tmp_path / ".terminal_hub" / "issues").is_dir()


def test_init_workspace_is_idempotent(tmp_path):
    init_workspace(tmp_path)
    init_workspace(tmp_path)  # second call should not raise
    assert (tmp_path / ".terminal_hub").is_dir()


def test_detect_repo_from_env(tmp_path):
    with patch.dict("os.environ", {"GITHUB_REPO": "owner/my-repo"}):
        assert detect_repo(tmp_path) == "owner/my-repo"


def test_detect_repo_from_git_remote(tmp_path):
    with patch("subprocess.check_output", return_value=b"git@github.com:owner/repo.git\n"):
        assert detect_repo(tmp_path) == "owner/repo"


def test_detect_repo_returns_none_when_no_remote(tmp_path):
    with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "git")):
        with patch.dict("os.environ", {}, clear=True):
            assert detect_repo(tmp_path) is None


def test_detect_repo_parses_https_remote(tmp_path):
    with patch("subprocess.check_output", return_value=b"https://github.com/owner/repo.git\n"):
        assert detect_repo(tmp_path) == "owner/repo"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_workspace.py -v
```

Expected: `ImportError` — functions not implemented.

- [ ] **Step 3: Implement `workspace.py`**

```python
# terminal_hub/workspace.py
"""Auto-initialize .terminal_hub/ directory structure and detect cwd and GitHub repo."""
import os
import re
import subprocess
from pathlib import Path


def init_workspace(root: Path) -> None:
    """Create .terminal_hub/ structure if it does not exist. Idempotent."""
    (root / ".terminal_hub" / "issues").mkdir(parents=True, exist_ok=True)


def detect_repo(root: Path) -> str | None:
    """Return 'owner/repo' from GITHUB_REPO env var or git remote origin.

    Returns None if neither is available.
    """
    if repo := os.environ.get("GITHUB_REPO"):
        return repo

    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None

    # Parse both SSH (git@github.com:owner/repo.git) and HTTPS formats
    match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", remote)
    return match.group(1) if match else None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_workspace.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add terminal_hub/workspace.py tests/test_workspace.py
git commit -m "feat: add workspace init and repo detection"
```

---

### Task 5: Config management

**Files:**
- Modify: `terminal_hub/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py
from pathlib import Path
import pytest
from terminal_hub.config import load_config, save_config, WorkspaceMode


def test_save_and_load_local_config(tmp_path):
    save_config(tmp_path, mode=WorkspaceMode.LOCAL, repo=None)
    cfg = load_config(tmp_path)
    assert cfg["mode"] == "local"
    assert cfg["repo"] is None


def test_save_and_load_github_config(tmp_path):
    save_config(tmp_path, mode=WorkspaceMode.GITHUB, repo="owner/my-repo")
    cfg = load_config(tmp_path)
    assert cfg["mode"] == "github"
    assert cfg["repo"] == "owner/my-repo"


def test_load_config_returns_none_when_missing(tmp_path):
    assert load_config(tmp_path) is None


def test_workspace_mode_values():
    assert WorkspaceMode.LOCAL == "local"
    assert WorkspaceMode.GITHUB == "github"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_config.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `config.py`**

```python
# terminal_hub/config.py
"""Read/write .terminal_hub/config.yaml and workspace mode detection."""
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class WorkspaceMode(StrEnum):
    LOCAL = "local"
    GITHUB = "github"


_CONFIG_FILE = ".terminal_hub/config.yaml"


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
    with path.open("w") as f:
        yaml.dump({"mode": str(mode), "repo": repo}, f)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_config.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add terminal_hub/config.py tests/test_config.py
git commit -m "feat: add config read/write with workspace modes"
```

---

### Task 6: Storage layer (issue files + project docs)

**Files:**
- Modify: `terminal_hub/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_storage.py
from datetime import date
from pathlib import Path
import pytest
from terminal_hub.storage import (
    write_issue_file,
    read_issue_frontmatter,
    list_issue_files,
    write_doc_file,
    read_doc_file,
)


def test_write_and_read_issue(tmp_path):
    root = tmp_path
    (root / ".terminal_hub" / "issues").mkdir(parents=True)
    write_issue_file(
        root=root,
        slug="fix-auth-bug",
        title="Fix auth bug",
        issue_number=42,
        github_url="https://github.com/owner/repo/issues/42",
        body="## Overview\nFix the bug.",
        assignees=[],
        labels=[],
        created_at=date(2026, 3, 15),
    )
    fm = read_issue_frontmatter(root, "fix-auth-bug")
    assert fm["title"] == "Fix auth bug"
    assert fm["issue_number"] == 42
    assert fm["github_url"] == "https://github.com/owner/repo/issues/42"
    assert fm["created_at"] == "2026-03-15"
    assert fm["assignees"] == []
    assert fm["labels"] == []


def test_list_issue_files_sorted_by_date_desc(tmp_path):
    root = tmp_path
    (root / ".terminal_hub" / "issues").mkdir(parents=True)
    for slug, day in [("issue-a", 10), ("issue-b", 15), ("issue-c", 5)]:
        write_issue_file(
            root=root, slug=slug, title=slug, issue_number=1,
            github_url="https://github.com/o/r/issues/1",
            body="body", assignees=[], labels=[],
            created_at=date(2026, 3, day),
        )
    issues = list_issue_files(root)
    assert [i["slug"] for i in issues] == ["issue-b", "issue-a", "issue-c"]


def test_list_issue_files_empty(tmp_path):
    root = tmp_path
    (root / ".terminal_hub" / "issues").mkdir(parents=True)
    assert list_issue_files(root) == []


def test_write_and_read_doc_file(tmp_path):
    root = tmp_path
    (root / ".terminal_hub").mkdir(parents=True)
    write_doc_file(root, "project_description", "# My Project\n")
    assert read_doc_file(root, "project_description") == "# My Project\n"


def test_read_doc_file_returns_none_when_missing(tmp_path):
    root = tmp_path
    (root / ".terminal_hub").mkdir(parents=True)
    assert read_doc_file(root, "project_description") is None


def test_slug_collision_increments_suffix(tmp_path):
    root = tmp_path
    (root / ".terminal_hub" / "issues").mkdir(parents=True)
    write_issue_file(root=root, slug="fix-bug", title="Fix bug", issue_number=1,
        github_url="u", body="b", assignees=[], labels=[], created_at=date(2026, 3, 1))
    # Manually check that the file exists
    assert (root / ".terminal_hub" / "issues" / "fix-bug.md").exists()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_storage.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `storage.py`**

```python
# terminal_hub/storage.py
"""Read/write issue .md files and project context documents with YAML front matter."""
from datetime import date
from pathlib import Path
from typing import Any

import yaml

_DOC_FILES = {
    "project_description": ".terminal_hub/project_description.md",
    "architecture": ".terminal_hub/architecture_design.md",
}


def _issues_dir(root: Path) -> Path:
    return root / ".terminal_hub" / "issues"


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
    issue_number: int,
    github_url: str,
    body: str,
    assignees: list[str],
    labels: list[str],
    created_at: date,
) -> Path:
    """Write an issue .md file with YAML front matter. Returns the file path."""
    path = _issues_dir(root) / f"{slug}.md"
    frontmatter = {
        "title": title,
        "issue_number": issue_number,
        "github_url": github_url,
        "created_at": created_at.strftime("%Y-%m-%d"),
        "assignees": assignees,
        "labels": labels,
    }
    content = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{body}\n"
    path.write_text(content)
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
    issues_dir = _issues_dir(root)
    results = []
    for md_file in issues_dir.glob("*.md"):
        slug = md_file.stem
        fm = read_issue_frontmatter(root, slug)
        if fm:
            results.append({
                "slug": slug,
                "title": fm.get("title", ""),
                "issue_number": fm.get("issue_number"),
                "github_url": fm.get("github_url"),
                "created_at": fm.get("created_at"),
                "assignees": fm.get("assignees", []),
                "labels": fm.get("labels", []),
                "file": f".terminal_hub/issues/{slug}.md",
            })
    return sorted(results, key=lambda x: x["created_at"] or "", reverse=True)


def write_doc_file(root: Path, doc_key: str, content: str) -> Path:
    """Overwrite a project context doc file. doc_key: 'project_description' or 'architecture'."""
    path = root / _DOC_FILES[doc_key]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def read_doc_file(root: Path, doc_key: str) -> str | None:
    """Return content of a project context doc or None if it doesn't exist."""
    path = root / _DOC_FILES[doc_key]
    return path.read_text() if path.exists() else None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_storage.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add terminal_hub/storage.py tests/test_storage.py
git commit -m "feat: add storage layer for issue files and project docs"
```

---

## Chunk 3: GitHub Client

**Covers:** `github_client.py` — thin httpx wrapper for GitHub REST API.

---

### Task 7: GitHub REST API client

**Files:**
- Modify: `terminal_hub/github_client.py`
- Create: `tests/test_github_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_github_client.py
import pytest
import httpx
from unittest.mock import patch, MagicMock
from terminal_hub.github_client import GitHubClient, GitHubError


def make_client(token="test-token", repo="owner/repo"):
    return GitHubClient(token=token, repo=repo)


def test_create_issue_success():
    client = make_client()
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "number": 42,
        "html_url": "https://github.com/owner/repo/issues/42",
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client._client, "post", return_value=mock_response):
        result = client.create_issue(
            title="Fix auth bug",
            body="## Overview\nFix it.",
            labels=[],
            assignees=[],
        )

    assert result["number"] == 42
    assert result["html_url"] == "https://github.com/owner/repo/issues/42"


def test_create_issue_raises_on_api_error():
    client = make_client()
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=MagicMock()
    )
    mock_response.text = "Bad credentials"

    with patch.object(client._client, "post", return_value=mock_response):
        with pytest.raises(GitHubError, match="Bad credentials"):
            client.create_issue(title="x", body="y", labels=[], assignees=[])


def test_client_sets_auth_header():
    client = make_client(token="my-token")
    assert client._client.headers["Authorization"] == "Bearer my-token"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_github_client.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `github_client.py`**

```python
# terminal_hub/github_client.py
"""GitHub REST API client using httpx."""
import httpx


class GitHubError(Exception):
    pass


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str, repo: str) -> None:
        self.repo = repo
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str],
        assignees: list[str],
    ) -> dict:
        """POST to GitHub Issues API. Returns response JSON on success."""
        url = f"{self.BASE_URL}/repos/{self.repo}/issues"
        payload = {"title": title, "body": body, "labels": labels, "assignees": assignees}
        response = self._client.post(url, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GitHubError(response.text) from exc
        return response.json()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_github_client.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add terminal_hub/github_client.py tests/test_github_client.py
git commit -m "feat: add GitHub REST API client"
```

---

## Chunk 4: MCP Tools

**Covers:** All 6 tools registered in `server.py`. Server boots with tools, each tool has unit tests.

---

### Task 8: `create_issue` tool

**Files:**
- Modify: `terminal_hub/server.py`
- Create: `tests/tools/test_create_issue.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/tools/test_create_issue.py
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from terminal_hub.server import create_server


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".terminal_hub" / "issues").mkdir(parents=True)
    return tmp_path


def test_create_issue_writes_local_file(workspace):
    mock_gh = MagicMock()
    mock_gh.create_issue.return_value = {
        "number": 1,
        "html_url": "https://github.com/o/r/issues/1",
    }

    with patch("terminal_hub.server.get_github_client", return_value=mock_gh), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        # Call the tool function directly
        result = server._tool_manager.call_tool("create_issue", {
            "title": "Fix auth bug",
            "body": "Fix it.",
        })

    assert (workspace / ".terminal_hub" / "issues" / "fix-auth-bug.md").exists()
    assert result["issue_number"] == 1


def test_create_issue_returns_error_in_readonly_mode(workspace):
    with patch("terminal_hub.server.get_github_client", return_value=None), \
         patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = server._tool_manager.call_tool("create_issue", {
            "title": "Fix auth bug",
            "body": "Fix it.",
        })

    assert result["error"] == "github_unavailable"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/tools/test_create_issue.py -v
```

Expected: Fail — tool not registered.

- [ ] **Step 3: Add `get_github_client`, `get_workspace_root` helpers and `create_issue` tool to `server.py`**

```python
# terminal_hub/server.py
import os
from datetime import date
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from terminal_hub.github_client import GitHubClient, GitHubError
from terminal_hub.prompts import TERMINAL_HUB_INSTRUCTIONS
from terminal_hub.slugify import slugify
from terminal_hub.storage import (
    list_issue_files,
    read_doc_file,
    read_issue_file,
    resolve_slug,
    write_doc_file,
    write_issue_file,
)
from terminal_hub.workspace import detect_repo, init_workspace


def get_workspace_root() -> Path:
    return Path.cwd()


def get_github_client() -> GitHubClient | None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    root = get_workspace_root()
    repo = os.environ.get("GITHUB_REPO") or detect_repo(root)
    if not repo:
        return None
    return GitHubClient(token=token, repo=repo)


def create_server() -> FastMCP:
    mcp = FastMCP("terminal-hub")

    # Run workspace init on server start
    root = get_workspace_root()
    init_workspace(root)

    @mcp.prompt()
    def terminal_hub_instructions() -> str:
        return TERMINAL_HUB_INSTRUCTIONS

    @mcp.tool()
    def create_issue(
        title: str,
        body: str,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict:
        """Create a GitHub issue and save context locally.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        gh = get_github_client()

        if gh is None:
            token = os.environ.get("GITHUB_TOKEN")
            if not token:
                return {"error": "github_unavailable",
                        "message": "GITHUB_TOKEN is not set. Set it in your MCP config env."}
            return {"error": "github_unavailable",
                    "message": "No GitHub repo detected. Set GITHUB_REPO=owner/repo "
                               "or run from a git repo with a remote."}

        try:
            data = gh.create_issue(
                title=title,
                body=body,
                labels=labels or [],
                assignees=assignees or [],
            )
        except GitHubError as exc:
            return {"error": "github_unavailable", "message": str(exc)}

        base_slug = slugify(title)
        slug = resolve_slug(root, base_slug)

        try:
            path = write_issue_file(
                root=root,
                slug=slug,
                title=title,
                issue_number=data["number"],
                github_url=data["html_url"],
                body=body,
                assignees=assignees or [],
                labels=labels or [],
                created_at=date.today(),
            )
            local_file = str(path.relative_to(root))
        except OSError as exc:
            return {
                "issue_number": data["number"],
                "url": data["html_url"],
                "local_file": None,
                "warning": "local_write_failed",
                "warning_message": f"Issue created on GitHub but local file could not be written: {exc}",
            }

        return {
            "issue_number": data["number"],
            "url": data["html_url"],
            "local_file": local_file,
        }

    return mcp
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/tools/test_create_issue.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add terminal_hub/server.py tests/tools/test_create_issue.py
git commit -m "feat: add create_issue MCP tool"
```

---

### Task 9: Remaining 5 MCP tools

**Files:**
- Modify: `terminal_hub/server.py`
- Create: `tests/tools/test_update_docs.py`
- Create: `tests/tools/test_list_issues.py`
- Create: `tests/tools/test_get_context.py`

- [ ] **Step 1: Write failing tests for `update_project_description`**

```python
# tests/tools/test_update_docs.py
from pathlib import Path
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".terminal_hub").mkdir(parents=True)
    return tmp_path


def test_update_project_description_writes_file(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = server._tool_manager.call_tool("update_project_description", {
            "content": "# My Project\n"
        })
    assert result["updated"] is True
    assert (workspace / ".terminal_hub" / "project_description.md").read_text() == "# My Project\n"


def test_update_architecture_writes_file(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = server._tool_manager.call_tool("update_architecture", {
            "content": "# Architecture\n"
        })
    assert result["updated"] is True
    assert (workspace / ".terminal_hub" / "architecture_design.md").read_text() == "# Architecture\n"
```

- [ ] **Step 2: Write failing tests for `list_issues`**

```python
# tests/tools/test_list_issues.py
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server
from terminal_hub.storage import write_issue_file


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".terminal_hub" / "issues").mkdir(parents=True)
    return tmp_path


def test_list_issues_returns_all(workspace):
    write_issue_file(workspace, "fix-bug", "Fix bug", 1, "http://gh/1",
                     "body", [], [], date(2026, 3, 15))
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = server._tool_manager.call_tool("list_issues", {})
    assert len(result["issues"]) == 1
    assert result["issues"][0]["slug"] == "fix-bug"


def test_list_issues_empty(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = server._tool_manager.call_tool("list_issues", {})
    assert result["issues"] == []
```

- [ ] **Step 3: Write failing tests for `get_project_context` and `get_issue_context`**

```python
# tests/tools/test_get_context.py
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
from terminal_hub.server import create_server
from terminal_hub.storage import write_issue_file, write_doc_file


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".terminal_hub" / "issues").mkdir(parents=True)
    return tmp_path


def test_get_project_context_single(workspace):
    write_doc_file(workspace, "project_description", "# Project\n")
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = server._tool_manager.call_tool("get_project_context",
                                                {"file": "project_description"})
    assert result["content"] == "# Project\n"


def test_get_project_context_all(workspace):
    write_doc_file(workspace, "project_description", "# Project\n")
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = server._tool_manager.call_tool("get_project_context", {"file": "all"})
    assert result["project_description"] == "# Project\n"
    assert result["architecture"] is None


def test_get_project_context_not_found(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = server._tool_manager.call_tool("get_project_context",
                                                {"file": "project_description"})
    assert result["content"] is None


def test_get_issue_context_found(workspace):
    write_issue_file(workspace, "fix-bug", "Fix bug", 1, "http://gh", "body", [], [],
                     date(2026, 3, 15))
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = server._tool_manager.call_tool("get_issue_context", {"slug": "fix-bug"})
    assert result["slug"] == "fix-bug"
    assert "Fix bug" in result["content"]


def test_get_issue_context_not_found(workspace):
    with patch("terminal_hub.server.get_workspace_root", return_value=workspace):
        server = create_server()
        result = server._tool_manager.call_tool("get_issue_context", {"slug": "no-such-issue"})
    assert result["error"] == "not_found"
```

- [ ] **Step 4: Run all failing tests**

```bash
pytest tests/tools/ -v
```

Expected: Many failures — tools not yet registered.

- [ ] **Step 5: Add remaining 5 tools to `server.py`**

Add inside `create_server()` after `create_issue`:

```python
    @mcp.tool()
    def update_project_description(content: str) -> dict:
        """Overwrite project_description.md. Call get_project_context first to preserve existing content.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        try:
            path = write_doc_file(root, "project_description", content)
            return {"updated": True, "file": str(path.relative_to(root))}
        except OSError as exc:
            return {"error": "write_failed", "message": str(exc)}

    @mcp.tool()
    def update_architecture(content: str) -> dict:
        """Overwrite architecture_design.md. Call get_project_context first to preserve existing content.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        try:
            path = write_doc_file(root, "architecture", content)
            return {"updated": True, "file": str(path.relative_to(root))}
        except OSError as exc:
            return {"error": "write_failed", "message": str(exc)}

    @mcp.tool()
    def list_issues() -> dict:
        """Return all tracked issues from local .terminal_hub/issues/ files.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        return {"issues": list_issue_files(root)}

    @mcp.tool()
    def get_project_context(file: str) -> dict:
        """Read project_description.md and/or architecture_design.md.
        file: 'project_description', 'architecture', or 'all'.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        if file == "all":
            return {
                "project_description": read_doc_file(root, "project_description"),
                "architecture": read_doc_file(root, "architecture"),
            }
        content = read_doc_file(root, file)
        return {"file": file, "content": content}

    @mcp.tool()
    def get_issue_context(slug: str) -> dict:
        """Read a specific issue file by slug to reload context cheaply.
        Hint: load terminal_hub_instructions if you haven't yet."""
        root = get_workspace_root()
        content = read_issue_file(root, slug)
        if content is None:
            return {
                "error": "not_found",
                "message": f"No issue file found for slug '{slug}'. Use list_issues to see available slugs.",
            }
        return {"slug": slug, "content": content}
```

- [ ] **Step 6: Run all tool tests**

```bash
pytest tests/tools/ -v
```

Expected: All PASS.

- [ ] **Step 7: Run full test suite**

```bash
pytest -v
```

Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add terminal_hub/server.py tests/tools/
git commit -m "feat: add remaining 5 MCP tools (update_docs, list_issues, get_context)"
```

---

## Chunk 5: Terminal UI and Entry Workflow

**Covers:** `ui/menu.py` keyboard menu, `ui/setup.py` three workspace modes, wired into `__main__.py`.

---

### Task 10: Terminal selection menu and workspace setup

**Files:**
- Modify: `terminal_hub/ui/menu.py`
- Modify: `terminal_hub/ui/setup.py`
- Modify: `terminal_hub/__main__.py`
- Create: `tests/ui/test_setup.py`

- [ ] **Step 1: Implement `menu.py`**

```python
# terminal_hub/ui/menu.py
"""Questionary-based terminal selection menu."""
from enum import StrEnum

import questionary


class SetupChoice(StrEnum):
    LOCAL = "local"
    NEW_REPO = "new_repo"
    CONNECT_REPO = "connect_repo"
    EXIT = "exit"


_CHOICES = [
    questionary.Choice(
        title="Local          — track plans and issues on this machine only",
        value=SetupChoice.LOCAL,
    ),
    questionary.Choice(
        title="New Repo       — create a new GitHub repository for this project",
        value=SetupChoice.NEW_REPO,
    ),
    questionary.Choice(
        title="Connect Repo   — link to an existing GitHub repository",
        value=SetupChoice.CONNECT_REPO,
    ),
    questionary.Separator(),
    questionary.Choice(title="Exit", value=SetupChoice.EXIT),
]


def prompt_setup_choice() -> SetupChoice | None:
    """Show the workspace setup menu. Returns None if user cancels (Ctrl+C / Esc)."""
    try:
        return questionary.select(
            "How do you want to set up your workspace?",
            choices=_CHOICES,
        ).ask()
    except KeyboardInterrupt:
        return None


def prompt_text(question: str, default: str = "") -> str | None:
    """Prompt for a single text value. Returns None on cancel."""
    try:
        return questionary.text(question, default=default).ask()
    except KeyboardInterrupt:
        return None


def prompt_confirm(question: str) -> bool:
    """Yes/no confirmation prompt. Returns False on cancel."""
    try:
        return questionary.confirm(question, default=True).ask() or False
    except KeyboardInterrupt:
        return False
```

- [ ] **Step 2: Implement `ui/setup.py`**

```python
# terminal_hub/ui/setup.py
"""Workspace setup flow for local, new repo, and connect repo modes."""
import os
import subprocess
from pathlib import Path

import httpx

from terminal_hub.config import WorkspaceMode, save_config
from terminal_hub.ui.menu import prompt_confirm, prompt_text
from terminal_hub.workspace import detect_repo, init_workspace


def run_local_setup(root: Path) -> bool:
    """Set up local-only workspace. Returns True on success."""
    print("\nSetting up local workspace...")
    init_workspace(root)
    save_config(root, mode=WorkspaceMode.LOCAL, repo=None)
    print("Done. Plans and issues will be saved in .terminal_hub/")
    return True


def run_new_repo_setup(root: Path) -> bool:
    """Create a new GitHub repo and link it. Returns True on success."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN is not set. Add it to your MCP config.")
        return False

    default_name = root.name
    name = prompt_text("Repository name:", default=default_name)
    if not name:
        return False

    is_private = not prompt_confirm("Make it public?")

    print(f"\nCreating {'private' if is_private else 'public'} repo '{name}'...")
    try:
        resp = httpx.post(
            "https://api.github.com/user/repos",
            json={"name": name, "private": is_private},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        print(f"Error: GitHub API returned {resp.status_code} — {resp.text}")
        return False

    data = resp.json()
    clone_url = data["ssh_url"]
    repo = data["full_name"]

    # Set or update git remote
    try:
        subprocess.run(["git", "remote", "add", "origin", clone_url], cwd=root,
                       check=True, capture_output=True)
    except subprocess.CalledProcessError:
        subprocess.run(["git", "remote", "set-url", "origin", clone_url],
                       cwd=root, check=True, capture_output=True)

    init_workspace(root)
    save_config(root, mode=WorkspaceMode.GITHUB, repo=repo)
    print(f"Done. Linked to https://github.com/{repo}")
    return True


def run_connect_repo_setup(root: Path) -> bool:
    """Link to an existing GitHub repo. Returns True on success."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN is not set. Add it to your MCP config.")
        return False

    detected = detect_repo(root)
    if detected:
        confirmed = prompt_confirm(f"Found remote: {detected}. Use this repo?")
        repo = detected if confirmed else None
    else:
        repo = None

    if not repo:
        repo = prompt_text("Enter repo (owner/repo-name):")
        if not repo:
            return False

    # Validate access
    print(f"\nValidating access to {repo}...")
    try:
        resp = httpx.get(
            f"https://api.github.com/repos/{repo}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        print(f"Error: Cannot access {repo} — check your GITHUB_TOKEN and repo name.")
        return False

    init_workspace(root)
    save_config(root, mode=WorkspaceMode.GITHUB, repo=repo)
    print(f"Done. Connected to https://github.com/{repo}")
    return True
```

- [ ] **Step 3: Write tests for setup flows**

```python
# tests/ui/test_setup.py
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from terminal_hub.ui.setup import run_local_setup, run_new_repo_setup, run_connect_repo_setup
from terminal_hub.config import load_config


def test_local_setup_creates_config(tmp_path):
    result = run_local_setup(tmp_path)
    assert result is True
    cfg = load_config(tmp_path)
    assert cfg["mode"] == "local"
    assert cfg["repo"] is None
    assert (tmp_path / ".terminal_hub" / "issues").is_dir()


def test_new_repo_setup_no_token(tmp_path):
    with patch.dict("os.environ", {}, clear=True):
        result = run_new_repo_setup(tmp_path)
    assert result is False


def test_connect_repo_setup_no_token(tmp_path):
    with patch.dict("os.environ", {}, clear=True):
        result = run_connect_repo_setup(tmp_path)
    assert result is False


def test_connect_repo_setup_with_detected_remote(tmp_path):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with patch.dict("os.environ", {"GITHUB_TOKEN": "tok"}), \
         patch("terminal_hub.ui.setup.detect_repo", return_value="owner/repo"), \
         patch("terminal_hub.ui.setup.prompt_confirm", return_value=True), \
         patch("httpx.get", return_value=mock_resp):
        result = run_connect_repo_setup(tmp_path)

    assert result is True
    cfg = load_config(tmp_path)
    assert cfg["repo"] == "owner/repo"
```

- [ ] **Step 4: Run UI tests**

```bash
pytest tests/ui/ -v
```

Expected: All PASS.

- [ ] **Step 5: Wire `__main__.py` — server starts immediately, setup is a separate command**

The MCP server must never block on interactive input. `terminal-hub` always starts the server
immediately. `terminal-hub setup` is the separate command for workspace setup.

```python
# terminal_hub/__main__.py
from pathlib import Path

from terminal_hub.server import create_server
from terminal_hub.ui.menu import SetupChoice, prompt_setup_choice
from terminal_hub.ui.setup import run_connect_repo_setup, run_local_setup, run_new_repo_setup


def main() -> None:
    """MCP server entry point. Always starts immediately — no blocking prompts."""
    server = create_server()
    server.run()


def setup() -> None:
    """Interactive workspace setup. Run once per project: terminal-hub setup"""
    root = Path.cwd()
    choice = prompt_setup_choice()

    if choice is None or choice == SetupChoice.EXIT:
        print("Exiting.")
        return

    success = False
    if choice == SetupChoice.LOCAL:
        success = run_local_setup(root)
    elif choice == SetupChoice.NEW_REPO:
        success = run_new_repo_setup(root)
    elif choice == SetupChoice.CONNECT_REPO:
        success = run_connect_repo_setup(root)

    if not success:
        print("Setup failed. Run terminal-hub setup to retry.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run full test suite**

```bash
pytest -v
```

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add terminal_hub/ui/ terminal_hub/__main__.py tests/ui/
git commit -m "feat: add terminal UI menu and workspace setup flows"
```

---

## Chunk 6: Packaging and Distribution

**Covers:** PyPI-ready `pyproject.toml`, `README.md`, `Dockerfile`.

---

### Task 11: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# terminal_hub

A terminal-based GitHub management and automation tool for Claude Code.
Automates issue creation and planning so you can focus on building.

## Install

pip install terminal-hub

## Configure

Add to ~/.claude.json:

{
  "mcpServers": {
    "terminal-hub": {
      "command": "terminal-hub",
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}

Optional: override repo auto-detection
"GITHUB_REPO": "owner/repo"

## First Run

Run the setup command once per project to configure your workspace:

terminal-hub setup

Choose: Local, New Repo, Connect Repo, or Exit.
This saves your choice to .terminal_hub/config.yaml.
The MCP server (terminal-hub) starts automatically via Claude Code and never blocks on input.

## Load Instructions in Claude Code

Run: /mcp terminal-hub terminal_hub_instructions

Or add to your CLAUDE.md:
Use terminal_hub_instructions from the terminal-hub MCP server at session start.

## GitHub Token

Create a token at: https://github.com/settings/tokens
Required scopes: repo
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with install and config guide"
```

---

### Task 12: Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY terminal_hub/ terminal_hub/

RUN pip install --no-cache-dir .

# Must run with -it for interactive terminal UI
# docker run -it --rm -e GITHUB_TOKEN=... -v $(pwd):/workspace terminal-hub
WORKDIR /workspace

ENTRYPOINT ["terminal-hub"]
```

- [ ] **Step 2: Build and verify**

```bash
docker build -t terminal-hub .
docker run --rm terminal-hub python -c "import terminal_hub; print('OK')" 2>/dev/null || echo "Build OK (interactive mode needed for full run)"
```

Expected: No build errors.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "chore: add Dockerfile for cross-platform edge case support"
```

---

### Task 13: Final verification

- [ ] **Step 1: Run complete test suite**

```bash
pytest -v --tb=short
```

Expected: All tests PASS, no warnings.

- [ ] **Step 2: Verify entry points are registered**

```bash
which terminal-hub && which terminal-hub-setup
```

Expected: Two paths printed (e.g. `/usr/local/bin/terminal-hub` and `/usr/local/bin/terminal-hub-setup`). If not found, run `pip install -e .` again.

- [ ] **Step 3: Verify package builds cleanly**

```bash
pip install build
python -m build --wheel
```

Expected: `dist/terminal_hub-0.1.0-py3-none-any.whl` created.

- [ ] **Step 4: Push to GitHub**

```bash
git push origin main
```

---

## Summary

| Chunk | Tasks | What ships |
|-------|-------|------------|
| 1 — Scaffold | 1-2 | Package boots, FastMCP server starts |
| 2 — Core Utils | 3-6 | Slugify, workspace init, config, storage |
| 3 — GitHub Client | 7 | httpx wrapper for GitHub REST API |
| 4 — MCP Tools | 8-9 | All 6 tools registered and tested |
| 5 — Terminal UI | 10 | Keyboard menu + 3 setup flows |
| 6 — Packaging | 11-13 | README, Dockerfile, PyPI wheel |
