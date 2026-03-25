"""Issue management — drafting, submitting, syncing, and context helpers."""
# stdlib
import json
import time
from datetime import date
from pathlib import Path


def _pkg():
    """Return the github_planner package module so patches applied by tests are respected."""
    import sys
    return sys.modules['extensions.gh_management.github_planner']

from terminal_hub.constants import ISSUES_SYNC_TTL

# ── Constants ─────────────────────────────────────────────────────────────────
_ISSUES_SYNC_TTL = ISSUES_SYNC_TTL


def _extract_design_refs(
    title: str,
    labels: list[str],
    resolved: str,
) -> tuple[list[str], list[str]]:
    """Extract matching design refs and rule bullets from loaded project docs."""
    from extensions.gh_management.github_planner.project_docs import _PROJECT_DOCS_CACHE

    entry = _PROJECT_DOCS_CACHE.get(resolved)
    if not entry:
        return [], []

    _STOPWORDS = {"fix", "feat", "add", "update", "the", "a", "an", "for", "in",
                  "to", "of", "and", "or", "with", "from", "on", "at", "by", "is"}
    raw_words = set((title + " " + " ".join(labels)).lower().replace("-", " ").replace(":", " ").split())
    keywords = raw_words - _STOPWORDS

    refs: list[str] = []
    rules: list[str] = []

    summary = entry.get("summary", "") or ""
    if summary and keywords:
        in_principles = False
        matched_rules: list[str] = []
        for line in summary.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("## design principles"):
                in_principles = True
                continue
            if in_principles:
                if stripped.startswith("## "):
                    break
                if stripped.startswith("- "):
                    principle = stripped[2:]
                    if any(kw in principle.lower() for kw in keywords):
                        matched_rules.append(principle)
        if matched_rules:
            refs.append("project_summary.md § Design Principles")
            for p in matched_rules[:5]:
                words = p.split()
                rules.append(" ".join(words[:12]) + ("…" if len(words) > 12 else ""))

    sections = entry.get("_sections") or {}
    for section_name in sections:
        section_lower = section_name.lower()
        if any(kw in section_lower for kw in keywords):
            ref = f"project_detail.md § {section_name}"
            if ref not in refs:
                refs.append(ref)

    return refs[:6], rules[:5]


def _format_design_context_display(refs: list[str], rules: list[str]) -> str:
    """Build design context block for _display. Returns empty string if refs is empty."""
    if not refs:
        return ""
    lines = ["\n\n→ Design refs"]
    for ref in refs:
        lines.append(f"   {ref}")
    if rules:
        lines.append("▸ Rules applied")
        for rule in rules:
            lines.append(f"   • {rule}")
    return "\n".join(lines)


def _format_design_context_body(refs: list[str], rules: list[str]) -> str:
    """Build ## Design Context section for issue body. Returns empty string if refs is empty."""
    if not refs:
        return ""
    ref_list = "\n".join(f"- `{r}`" for r in refs)
    body = f"\n\n## Design Context\n\n{ref_list}"
    if rules:
        rule_list = "\n".join(f"- {r}" for r in rules)
        body += f"\n\n**Relevant principles:**\n{rule_list}"
    return body


def _check_suggest_unload() -> str | None:
    """Return an unload suggestion string when session caches are heavy."""
    from extensions.gh_management.github_planner.analysis import _ANALYSIS_CACHE
    from extensions.gh_management.github_planner.project_docs import _PROJECT_DOCS_CACHE
    from extensions.gh_management.github_planner.labels import _LABEL_CACHE

    if _ANALYSIS_CACHE and _PROJECT_DOCS_CACHE and _LABEL_CACHE:
        return (
            "Context is getting heavy. Say 'unload github issue manager' to free memory "
            "and keep things fast, or continue working."
        )
    return None


def _issues_cache_stale(root: Path) -> bool:
    """Return True if local issue cache is empty or older than _ISSUES_SYNC_TTL."""
    from extensions.gh_management.github_planner.labels import _local_config_path

    config_path = _local_config_path(root)
    if not config_path.exists():
        return True
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        synced_at = data.get("issues_synced_at")
        if not synced_at:
            return True
        return (time.time() - float(synced_at)) > _ISSUES_SYNC_TTL
    except (json.JSONDecodeError, OSError, ValueError):
        return True


def _do_draft_issue(
    title: str,
    body: str,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    note: str | None = None,
    agent_workflow: list[str] | None = None,
    milestone_number: int | None = None,
) -> dict:
    """Save an issue draft locally as status=pending."""
    from extensions.gh_management.github_planner.storage import (
        IssueStatus, next_local_number
    )
    from terminal_hub.errors import msg
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    if not title:
        return {"error": "draft_failed", "message": msg("missing_field", detail="title"), "_hook": None}
    if not body:
        return {"error": "draft_failed", "message": msg("missing_field", detail="body"), "_hook": None}

    labels = labels or []
    assignees = assignees or []

    resolved = _p._resolve_repo(None) or "unknown"
    design_refs, design_rules = _extract_design_refs(title, labels, resolved)
    design_context_body = _format_design_context_body(design_refs, design_rules)
    full_body = body + design_context_body

    slug = next_local_number(root)

    try:
        _p.write_issue_file(
            root=root,
            slug=slug,
            title=title,
            body=full_body,
            assignees=assignees,
            labels=labels,
            created_at=date.today(),
            status=IssueStatus.PENDING,
            note=note,
            agent_workflow=agent_workflow,
            milestone_number=milestone_number,
            design_refs=design_refs or None,
        )
    except OSError as exc:
        return {"error": "draft_failed", "message": msg("draft_failed", detail=str(exc)), "_hook": None}

    display = f"📝 **Drafted:** {title} [slug: {slug}]" + _format_design_context_display(design_refs, design_rules)
    result = {
        "slug": slug,
        "title": title,
        "status": str(IssueStatus.PENDING),
        "_display": display,
        "detail": {
            "preview_body": body[:300] + ("…" if len(body) > 300 else ""),
            "labels": labels,
            "assignees": assignees,
            "local_file": f"hub_agents/issues/{slug}.md",
        },
    }
    if milestone_number is not None:
        result["milestone_number"] = milestone_number
    if design_refs:
        result["design_refs"] = design_refs
    _p._silent_skill_detection(root)
    return result


def _do_submit_issue(slug: str) -> dict:
    """Submit a pending local issue draft to GitHub."""
    from extensions.gh_management.github_planner.storage import (
        IssueStatus, validate_slug, read_issue_frontmatter, read_issue_file, update_issue_status
    )
    from extensions.gh_management.github_planner.client import GitHubError
    from extensions.gh_management.github_planner.milestones import _MILESTONE_CACHE
    from terminal_hub.errors import msg
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    try:
        validate_slug(slug)
    except ValueError:
        return {"error": "submit_failed", "message": msg("not_found", detail=slug), "_hook": None}

    fm = read_issue_frontmatter(root, slug)
    if fm is None:
        return {"error": "submit_failed", "message": msg("not_found", detail=slug), "_hook": None}

    current_status = str(fm.get("status", "")).lower()
    if current_status == str(IssueStatus.OPEN):
        return {
            "error": "already_submitted",
            "message": f"Issue '{slug}' is already open on GitHub.",
            "issue_number": fm.get("issue_number"),
            "url": fm.get("github_url"),
            "_hook": None,
        }
    if current_status == str(IssueStatus.CLOSED):
        return {
            "error": "already_closed",
            "message": f"Issue '{slug}' is closed and cannot be re-submitted.",
            "_hook": None,
        }

    gh, error_message = _p.get_github_client()
    if gh is None:
        return {
            "error": "github_unavailable",
            "message": error_message,
            "_guidance": _p._G_AUTH,
            "_hook": None,
        }

    milestone_number = fm.get("milestone_number")
    if milestone_number:
        repo = _p.read_env(root).get("GITHUB_REPO", "")
        cached_milestones = _MILESTONE_CACHE.get(repo)
        if cached_milestones is not None:
            known_numbers = {m["number"] for m in cached_milestones}
            if milestone_number not in known_numbers:
                return {
                    "error": "milestone_not_found",
                    "milestone_number": milestone_number,
                    "_display": (
                        f"⚠️ **Milestone #{milestone_number} not found** on {repo}. "
                        "Remove the milestone assignment or run list_milestones() to see valid ones."
                    ),
                    "_hook": None,
                }

    labels: list[str] = fm.get("labels") or []
    raw = read_issue_file(root, slug) or ""
    body = raw.split("---", 2)[-1].strip() if raw.startswith("---") else raw

    with gh:
        if labels:
            label_err = gh.ensure_labels(labels)
            if label_err:
                return {"error": "label_bootstrap_failed", "message": label_err, "_hook": None}

        try:
            result = gh.create_issue(
                title=fm["title"],
                body=body,
                labels=labels,
                assignees=fm.get("assignees") or [],
            )
            if fm.get("milestone_number"):
                try:
                    gh.update_issue_milestone(result["number"], fm["milestone_number"])
                except Exception:
                    pass
        except GitHubError as exc:
            return {**exc.to_dict(), "_hook": None}

    update_issue_status(
        root, slug,
        status=IssueStatus.OPEN,
        issue_number=result["number"],
        github_url=result["html_url"],
    )

    return {
        "issue_number": result["number"],
        "url": result["html_url"],
        "slug": slug,
        "_display": f"✅ **Submitted:** #{result['number']} — {fm['title']} — {result['html_url']}",
    }


def _do_get_issue_context(slug: str) -> dict:
    from extensions.gh_management.github_planner.storage import validate_slug, read_issue_file
    from terminal_hub.errors import msg
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    try:
        validate_slug(slug)
    except ValueError:
        return {"error": "not_found", "message": msg("not_found", detail=slug), "_hook": None}

    content = read_issue_file(root, slug)
    if content is None:
        return {"error": "not_found", "message": msg("not_found", detail=slug), "_hook": None}
    return {"slug": slug, "content": content}


def _do_scan_issue_context(feature_areas: list[str]) -> dict:
    """Scan project_detail.md sections for code references relevant to feature_areas."""
    import re as _re
    _do_lookup_feature_section = _pkg()._do_lookup_feature_section

    findings: dict = {
        "reusable": [],
        "extend": [],
        "patterns": [],
        "pitfalls": [],
        "sections_scanned": [],
    }

    for area in feature_areas:
        result = _do_lookup_feature_section(area)
        section_text: str = result.get("section") or ""
        if not section_text:
            continue

        findings["sections_scanned"].append(result.get("feature") or area)

        for m in _re.finditer(r"(?:def|class)\s+(\w+)", section_text):
            name = m.group(1)
            ctx_start = max(0, m.start() - 120)
            ctx_end = min(len(section_text), m.end() + 120)
            context = section_text[ctx_start:ctx_end]
            path_m = _re.search(r"[\w./\-]+\.py", context)
            path = path_m.group(0) if path_m else ""
            findings["reusable"].append({"name": name, "path": path, "description": ""})

        for m in _re.finditer(r"(?:src|tests|extensions)/[\w./\-]+\.py", section_text):
            path = m.group(0)
            if not any(r.get("path") == path for r in findings["reusable"]):
                findings["patterns"].append(f"See: {path}")

        for m in _re.finditer(r"(?:warning|note|pitfall|caution|watch)[:\s]+(.+)", section_text, _re.IGNORECASE):
            pitfall = m.group(1).strip()[:200]
            if pitfall:
                findings["pitfalls"].append(pitfall)

    return findings


def _do_generate_issue_workflows(slug: str) -> dict:
    """Append agent + program workflow scaffolding to an existing issue file (#88)."""
    from extensions.gh_management.github_planner.storage import read_issue_frontmatter
    from extensions.gh_management.github_planner.skills import _SKILL_REGISTRY
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    fm = read_issue_frontmatter(root, slug)
    if not fm:
        return {"error": "issue_not_found", "message": f"No issue found for slug {slug!r}"}

    title = fm.get("title", slug)
    labels: list[str] = fm.get("labels") or []

    if any("bug" in lbl.lower() for lbl in labels):
        change_type = "bug fix"
    elif any(lbl in ("enhancement", "feature") for lbl in labels):
        change_type = "feature"
    elif any("refactor" in lbl.lower() for lbl in labels):
        change_type = "refactor"
    elif any("test" in lbl.lower() for lbl in labels):
        change_type = "test"
    elif any("doc" in lbl.lower() for lbl in labels):
        change_type = "documentation"
    else:
        change_type = "implementation"

    workflow_steps = [
        "orient: re-read issue, identify affected files",
        "plan: list changes, confirm approach fits codebase patterns",
        "implement: atomic, test-verified changes",
        "verify: all tests pass, coverage ≥ 80%, acceptance criteria met",
    ]

    registry = _SKILL_REGISTRY.get(str(root)) or {}
    if "intent-expansion" in registry:
        workflow_steps = [
            "expand-intent: apply intent-expansion skill — map to domain, apply conventions, filter by stack + design principles",
        ] + workflow_steps

    import re as _re_wf
    title_keywords = [w for w in _re_wf.split(r"[\s:/\-]+", title) if len(w) > 3]
    context_findings = _do_scan_issue_context(title_keywords[:4])
    affected_components_text = "<!-- Fill in: list files/modules that need to change -->"
    if context_findings.get("reusable") or context_findings.get("patterns"):
        refs = [f"- {r['name']} ({r['path']})" for r in context_findings["reusable"] if r.get("name")]
        refs += [f"- {p}" for p in context_findings["patterns"]]
        if refs:
            affected_components_text = "\n".join(refs[:8])

    agent_workflow_text = (
        f"Orient → read issue #{slug} carefully. "
        f"Change type: {change_type}. "
        "Plan minimal file changes, implement with test verification after each step, "
        "verify full suite passes before marking done."
    )

    workflow_body_section = f"""
---

## Agent Workflow

### 1. Orient
- Re-read this issue (Issue #{slug}) title and body carefully
- Identify the minimal set of files affected
- Understand the acceptance criteria before touching any code

### 2. Plan
- List files to change; prefer editing existing over creating new
- Confirm the approach fits existing patterns in the codebase

### 3. Implement
- Make atomic, test-verified changes
- Run `python -m pytest` after each logical change

### 4. Verify
- All tests pass
- Coverage ≥ 80%
- Acceptance criteria met

---

## Program Workflow

**Change type:** {change_type}

### Affected components
{affected_components_text}

### Test plan
- [ ] Unit tests for new/changed logic
- [ ] Update existing tests if behaviour changed
- [ ] No regressions (full suite passes)
"""

    issue_path = root / "hub_agents" / "issues" / f"{slug}.md"
    if not issue_path.exists():
        return {"error": "issue_not_found", "message": f"File missing: {issue_path}"}

    existing = issue_path.read_text(encoding="utf-8")
    if "## Agent Workflow" in existing:
        return {"slug": slug, "updated": False, "message": "Workflow section already present"}

    import yaml as _yaml
    import os as _os
    parts = existing.split("---", 2)
    raw_fm = _yaml.safe_load(parts[1]) or {}
    body_rest = parts[2] if len(parts) > 2 else ""
    if not raw_fm.get("workflow"):
        raw_fm["workflow"] = workflow_steps
    if not raw_fm.get("agent_workflow"):
        raw_fm["agent_workflow"] = agent_workflow_text
    updated_front = f"---\n{_yaml.dump(raw_fm, default_flow_style=False)}---\n{body_rest}"
    tmp = issue_path.with_suffix(".tmp")
    tmp.write_text(updated_front.rstrip() + workflow_body_section, encoding="utf-8")
    _os.replace(tmp, issue_path)

    _p._silent_skill_detection(root)
    return {
        "slug": slug,
        "updated": True,
        "file": f"hub_agents/issues/{slug}.md",
        "_display": f"✓ Workflow scaffold added to #{slug}",
    }


def _do_list_issues(compact: bool = False) -> dict:
    from extensions.gh_management.github_planner.storage import list_issue_files
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    issues = list_issue_files(root)
    for issue in issues:
        if not issue.get("issue_number"):
            issue["local_only"] = True
    if compact:
        compact_issues = []
        for i in issues:
            entry: dict = {"slug": i["slug"], "title": i["title"], "status": i["status"]}
            if i.get("local_only"):
                entry["local_only"] = True
            if i.get("design_refs"):
                entry["design_refs_count"] = len(i["design_refs"])
            compact_issues.append(entry)
        issues = compact_issues
    result: dict = {"issues": issues}
    if _issues_cache_stale(root):
        result["_suggest_sync"] = (
            "Issue cache is empty or stale. Call sync_github_issues() to fetch "
            "the latest issues from GitHub at ~30 tokens/issue instead of ~150."
        )
    if hint := _check_suggest_unload():
        result["_suggest_unload"] = hint
    return result


def _do_list_pending_drafts() -> dict:
    """Return only local-only (unsubmitted) issues."""
    from extensions.gh_management.github_planner.storage import list_issue_files
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err
    issues = list_issue_files(root)
    pending = [
        {"slug": i["slug"], "title": i["title"], "status": i["status"],
         "created_at": i.get("created_at"), "file": i.get("file")}
        for i in issues
        if not i.get("issue_number")
    ]
    return {"pending_drafts": pending, "count": len(pending)}


def _do_sync_github_issues(state: str = "open", refresh: bool = False) -> dict:
    """Two-phase GitHub issue sync (#204)."""
    import datetime as _dt
    from extensions.gh_management.github_planner.storage import (
        IssueStatus, list_issue_files, write_issue_file, update_issue_status
    )
    from extensions.gh_management.github_planner.labels import _do_save_github_local_config
    from terminal_hub.slugify import slugify
    _p = _pkg()

    root = _p.get_workspace_root()
    if err := _p.ensure_initialized(root):
        return err

    valid_states = {"open", "closed", "all"}
    if state not in valid_states:
        return {"error": "invalid_state", "message": f"state must be one of {sorted(valid_states)}"}

    gh, error_message = _p.get_github_client()
    if gh is None:
        return {"error": "github_unavailable", "message": error_message, "_guidance": _p._G_AUTH}

    with gh:
        try:
            raw_issues = gh.list_issues_all(state=state)
        except Exception as exc:
            return {"error": "github_error", "message": str(exc)}

    (root / "hub_agents" / "issues").mkdir(parents=True, exist_ok=True)

    local_index: dict[int, dict] = {}
    for fm in list_issue_files(root):
        num = fm.get("issue_number")
        if num:
            local_index[num] = {
                "slug": fm["slug"],
                "updated_at": fm.get("updated_at", ""),
                "status": fm.get("status", "open"),
            }

    total_raw = len(raw_issues)
    checked = 0
    updated = 0
    skipped = 0
    closed_locally = 0

    for raw in raw_issues:
        if raw.get("pull_request"):
            continue

        checked += 1
        number = raw.get("number")
        updated_at_str = raw.get("updated_at", "")
        github_state = raw.get("state", "open")

        if not refresh and number in local_index:
            local = local_index[number]
            if github_state == "closed" and str(local["status"]) == "open":
                from extensions.gh_management.github_planner.storage import update_issue_status
                update_issue_status(root, local["slug"], IssueStatus.CLOSED)
                closed_locally += 1
                continue
            if updated_at_str and updated_at_str == local["updated_at"]:
                skipped += 1
                continue

        title = raw.get("title", "")
        body = raw.get("body") or ""
        issue_state = raw.get("state", "open")
        labels = [lbl["name"] for lbl in raw.get("labels", [])]
        assignees = [a["login"] for a in raw.get("assignees", [])]
        created_at_str = raw.get("created_at", "")
        github_url = raw.get("html_url", "")
        milestone = raw.get("milestone") or {}
        milestone_number = milestone.get("number") if milestone else None
        milestone_title = milestone.get("title") if milestone else None

        try:
            created_date = _dt.datetime.fromisoformat(
                created_at_str.replace("Z", "+00:00")
            ).date()
        except (ValueError, AttributeError):
            created_date = date.today()

        issue_status = IssueStatus.OPEN if issue_state == "open" else IssueStatus.CLOSED

        base_slug = f"{number}-{slugify(title)}" if number else slugify(title)
        if not base_slug:
            base_slug = str(number or "unknown")
        slug = local_index[number]["slug"] if number in local_index else base_slug

        write_issue_file(
            root=root,
            slug=slug,
            title=title,
            body=body,
            assignees=assignees,
            labels=labels,
            created_at=created_date,
            status=issue_status,
            issue_number=number,
            github_url=github_url,
            milestone_number=milestone_number,
            milestone_title=milestone_title,
            updated_at=updated_at_str,
        )
        updated += 1

    _do_save_github_local_config({"issues_synced_at": time.time(), "issues_state": state})

    env = _p.read_env(root)
    repo = env.get("GITHUB_REPO", "unknown")
    return {
        "checked": checked,
        "updated": updated,
        "synced": updated,
        "skipped": skipped,
        "closed_locally": closed_locally,
        "total": total_raw,
        "state": state,
        "_display": (
            f"✓ Synced {updated} issue(s) from {repo} ({state})\n"
            f"  Skipped {skipped} unchanged | Closed locally: {closed_locally} | Checked: {checked}\n"
            f"  Stored in hub_agents/issues/"
        ),
    }
