"""gh_auxiliaries — community standards file generators for terminal-hub.

Registers MCP tools for generating GitHub community files (Code of Conduct,
Security Policy, PR/Issue templates, .gitignore) on explicit user request.

Tools:
  scan_community_metadata()                  — scan config files for project metadata
  save_community_metadata(...)               — persist metadata to hub_agents/community.json
  generate_and_write_coc(template_key, ...)  — fetch template, inject metadata, write file
  link_community_file(targets, filename)     — insert CoC link in README/CONTRIBUTING

Design note: CoC template content is fetched from official upstream URLs entirely
within Python (server-side). It never passes through Claude's context, avoiding
content-filter collisions on policy language.
"""
from __future__ import annotations

import json
import re
import tomllib
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from terminal_hub.workspace import resolve_workspace_root

# ── Template sources ───────────────────────────────────────────────────────────
# Templates fetched from official upstream at call time; never stored in repo.

_TEMPLATE_URLS: dict[str, str] = {
    "a": (
        "https://raw.githubusercontent.com/EthicalSource/contributor_covenant/"
        "release/content/version/2_1/code_of_conduct.md"
    ),
    "b": (
        "https://raw.githubusercontent.com/django/django-conduct/"
        "main/code_of_conduct.md"
    ),
    "c": (
        "https://raw.githubusercontent.com/stumpsyn/policies/"
        "master/citizen_code_of_conduct.md"
    ),
}

_TEMPLATE_NAMES: dict[str, str] = {
    "a": "Contributor Covenant v2.1",
    "b": "Django Code of Conduct",
    "c": "Citizen Code of Conduct",
}

# ── Metadata extraction ────────────────────────────────────────────────────────

def _community_json_path(root: Path) -> Path:
    return root / "hub_agents" / "community.json"


def _scan_pyproject(root: Path) -> dict[str, str]:
    path = root / "pyproject.toml"
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        project = data.get("project") or data.get("tool", {}).get("poetry", {})
        result: dict[str, str] = {}
        if name := project.get("name"):
            result["project_name"] = name
        authors = project.get("authors", [])
        if authors:
            first = authors[0]
            if isinstance(first, dict):
                if author_name := first.get("name"):
                    result["maintainer_name"] = author_name
                if email := first.get("email"):
                    result["contact_email"] = email
            elif isinstance(first, str):
                m = re.match(r"^(.+?)\s*<(.+?)>$", first)
                if m:
                    result["maintainer_name"] = m.group(1).strip()
                    result["contact_email"] = m.group(2).strip()
        return result
    except Exception:
        return {}


def _scan_package_json(root: Path) -> dict[str, str]:
    path = root / "package.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        result: dict[str, str] = {}
        if name := data.get("name"):
            result["project_name"] = name
        author = data.get("author", {})
        if isinstance(author, str):
            m = re.match(r"^(.+?)\s*<(.+?)>$", author)
            if m:
                result["maintainer_name"] = m.group(1).strip()
                result["contact_email"] = m.group(2).strip()
            else:
                result["maintainer_name"] = author
        elif isinstance(author, dict):
            if author_name := author.get("name"):
                result["maintainer_name"] = author_name
            if email := author.get("email"):
                result["contact_email"] = email
        bugs = data.get("bugs", {})
        if isinstance(bugs, dict) and "contact_email" not in result:
            if email := bugs.get("email"):
                result["contact_email"] = email
        return result
    except Exception:
        return {}


def _scan_codeowners(root: Path) -> dict[str, str]:
    for candidate in [root / ".github" / "CODEOWNERS", root / "CODEOWNERS"]:
        if candidate.exists():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split()
                        if len(parts) >= 2:
                            return {"maintainer_name": parts[1].lstrip("@")}
            except Exception:
                pass
    return {}


def _scan_readme(root: Path) -> dict[str, str]:
    path = root / "README.md"
    if not path.exists():
        return {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^#\s+(.+)", line)
            if m:
                return {"project_name": m.group(1).strip()}
    except Exception:
        pass
    return {}


def _merge_metadata(*sources: dict[str, str]) -> dict[str, str]:
    """Merge dicts; earlier sources take priority over later ones."""
    result: dict[str, str] = {}
    for source in reversed(sources):
        result.update(source)
    return result


def scan_project_metadata(root: Path) -> dict[str, Any]:
    sources: dict[str, dict[str, str]] = {
        "pyproject.toml": _scan_pyproject(root),
        "package.json": _scan_package_json(root),
        ".github/CODEOWNERS": _scan_codeowners(root),
        "README.md": _scan_readme(root),
    }
    merged = _merge_metadata(*list(sources.values()))
    if "contact_email" in merged and "enforcement_contact" not in merged:
        merged["enforcement_contact"] = merged["contact_email"]
    return {
        "metadata": merged,
        "sources": {k: v for k, v in sources.items() if v},
    }


def load_community_metadata(root: Path) -> dict | None:
    path = _community_json_path(root)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_community_json(metadata: dict, root: Path) -> Path:
    path = _community_json_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


# ── Template fetching + rendering ──────────────────────────────────────────────

def _fetch_url(url: str, timeout: int = 10) -> str | None:
    """Fetch text content from a URL. Returns None on any error."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return resp.read().decode("utf-8")
    except Exception:
        return None


def _inject_metadata(template_text: str, project_name: str, contact_email: str, enforcement_contact: str) -> str:
    """Replace known placeholder patterns across all three standard templates."""
    # Contributor Covenant v2.1 placeholders
    template_text = re.sub(r"\[INSERT CONTACT METHOD\]", enforcement_contact, template_text)
    template_text = re.sub(r"\[INSERT COMMUNITY SPACE NAME\]", project_name, template_text)
    # Generic {{}} placeholders (our own convention)
    template_text = template_text.replace("{{project_name}}", project_name)
    template_text = template_text.replace("{{contact_email}}", contact_email)
    template_text = template_text.replace("{{enforcement_contact}}", enforcement_contact)
    return template_text


# ── File linking ───────────────────────────────────────────────────────────────

def _insert_coc_link(file_path: Path, coc_filename: str) -> str:
    """Append a CoC reference section. Returns 'linked', 'already linked', or 'file not found'."""
    if not file_path.exists():
        return "file not found"
    text = file_path.read_text(encoding="utf-8")
    link_ref = f"[Code of Conduct]({coc_filename})"
    if link_ref in text or coc_filename in text:
        return "already linked"
    lines = text.rstrip("\n").splitlines()
    lines += ["", "## Code of Conduct", "", f"Please read our {link_ref} before contributing.", ""]
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "linked"


# ── Internal do_ functions ─────────────────────────────────────────────────────

def _do_scan_community_metadata() -> dict:
    root = resolve_workspace_root()
    result = scan_project_metadata(root)
    metadata: dict[str, str] = result["metadata"]
    sources: dict[str, dict] = result["sources"]

    cached = load_community_metadata(root)
    if cached:
        for k, v in cached.items():
            if k not in metadata:
                metadata[k] = v

    lines: list[str] = ["**Scanned project metadata**", ""]
    for src_name, fields in sources.items():
        if fields:
            lines.append(f"From `{src_name}`:")
            for k, v in fields.items():
                lines.append(f"  {k}: `{v}`")
    lines.append("")
    if metadata:
        lines.append("**Merged result:**")
        for k, v in metadata.items():
            lines.append(f"  {k}: `{v}`")
    else:
        lines.append("⚠️  No metadata found — enter values manually.")

    return {"metadata": metadata, "sources": sources, "_display": "\n".join(lines)}


def _do_save_community_metadata(
    project_name: str = "",
    maintainer_name: str = "",
    contact_email: str = "",
    enforcement_contact: str = "",
) -> dict:
    root = resolve_workspace_root()
    updated = load_community_metadata(root) or {}
    if project_name:
        updated["project_name"] = project_name
    if maintainer_name:
        updated["maintainer_name"] = maintainer_name
    if contact_email:
        updated["contact_email"] = contact_email
    if enforcement_contact:
        updated["enforcement_contact"] = enforcement_contact
    elif contact_email and "enforcement_contact" not in updated:
        updated["enforcement_contact"] = contact_email
    path = _write_community_json(updated, root)
    return {"metadata": updated, "path": str(path), "_display": f"✅ **community.json saved** — `{path}`"}


def _do_generate_and_write_coc(
    template_key: str,
    project_name: str,
    contact_email: str,
    enforcement_contact: str = "",
    filename: str = "CODE_OF_CONDUCT.md",
) -> dict:
    """Fetch template server-side, inject metadata, write to project root.

    CoC content never passes through Claude — fetch → inject → write happens entirely
    in Python, avoiding content-filter collisions on policy language.
    """
    if template_key not in _TEMPLATE_URLS:
        return {
            "error": "unknown_template",
            "message": f"Unknown key '{template_key}'. Valid: {list(_TEMPLATE_URLS.keys())}",
            "_display": f"❌ Unknown template `{template_key}` — use a/b/c",
        }
    if "/" in filename or "\\" in filename:
        return {
            "error": "invalid_filename",
            "message": f"filename must be a bare name: {filename!r}",
            "_display": f"❌ Invalid filename `{filename}`",
        }
    if not enforcement_contact:
        enforcement_contact = contact_email

    url = _TEMPLATE_URLS[template_key]
    raw = _fetch_url(url)
    if raw is None:
        return {
            "error": "fetch_failed",
            "message": f"Could not fetch template from {url}",
            "_display": f"❌ Network fetch failed for `{_TEMPLATE_NAMES[template_key]}` — check internet access",
        }

    content = _inject_metadata(raw, project_name, contact_email, enforcement_contact)
    root = resolve_workspace_root()
    target = root / filename
    target.write_text(content, encoding="utf-8")

    return {
        "template": _TEMPLATE_NAMES[template_key],
        "filename": filename,
        "path": str(target),
        "bytes_written": len(content.encode()),
        "_display": (
            f"✅ **{filename} written** ({len(content.encode())} bytes)\n"
            f"   Template: {_TEMPLATE_NAMES[template_key]}\n"
            f"   Path: `{target}`"
        ),
    }


def _do_link_community_file(targets: list[str], filename: str) -> dict:
    root = resolve_workspace_root()
    file_map = {"readme": "README.md", "contributing": "CONTRIBUTING.md"}
    results: dict[str, str] = {}
    for target in targets:
        if target not in file_map:
            results[target] = "skipped — use 'readme' or 'contributing'"
            continue
        results[target] = _insert_coc_link(root / file_map[target], filename)

    icons = {"linked": "✅", "already linked": "ℹ️", "file not found": "⚠️"}
    lines = ["**Link results**", ""]
    for t, status in results.items():
        lines.append(f"  {icons.get(status, '⚠️')} {t}: {status}")
    return {"results": results, "_display": "\n".join(lines)}


# ── Registration ───────────────────────────────────────────────────────────────

def register(mcp: FastMCP) -> None:
    """Register gh_auxiliaries MCP tools on the shared MCP server."""

    @mcp.tool()
    def scan_community_metadata() -> dict:
        """Scan project config files for metadata used to generate community standards files.

        Reads pyproject.toml, package.json, .github/CODEOWNERS, README.md.
        Extracts: project_name, maintainer_name, contact_email, enforcement_contact.
        Merges with any existing hub_agents/community.json cache.
        """
        return _do_scan_community_metadata()

    @mcp.tool()
    def save_community_metadata(
        project_name: str = "",
        maintainer_name: str = "",
        contact_email: str = "",
        enforcement_contact: str = "",
    ) -> dict:
        """Persist confirmed project metadata to hub_agents/community.json.

        Merges with existing community.json — only overwrites explicitly-provided fields.
        enforcement_contact defaults to contact_email if omitted.
        """
        return _do_save_community_metadata(
            project_name, maintainer_name, contact_email, enforcement_contact
        )

    @mcp.tool()
    def generate_and_write_coc(
        template_key: str,
        project_name: str,
        contact_email: str,
        enforcement_contact: str = "",
        filename: str = "CODE_OF_CONDUCT.md",
    ) -> dict:
        """Fetch a Code of Conduct template, inject metadata, and write to the project root.

        template_key: "a" (Contributor Covenant v2.1), "b" (Django CoC), "c" (Citizen CoC)
        filename: output filename (default: CODE_OF_CONDUCT.md)

        Template content is fetched from the official upstream URL entirely in Python —
        it never passes through Claude's context. Safe to call without content-filter risk.
        """
        return _do_generate_and_write_coc(
            template_key, project_name, contact_email, enforcement_contact, filename
        )

    @mcp.tool()
    def link_community_file(targets: list[str], filename: str) -> dict:
        """Insert a link to a community file in README.md and/or CONTRIBUTING.md.

        targets: list of "readme" and/or "contributing"
        filename: the file to reference (e.g. "CODE_OF_CONDUCT.md")
        Appends a ## Code of Conduct section — no-ops if the file is already linked.
        """
        return _do_link_community_file(targets, filename)
