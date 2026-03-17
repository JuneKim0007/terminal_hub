"""Repo intelligence analysis for github_planner."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


# ── Pure extraction functions ──────────────────────────────────────────────

def extract_label_patterns(issues: list[dict]) -> dict:
    """Return label frequency map and top-5 suggested labels."""
    freq: dict[str, int] = {}
    for issue in issues:
        for label in issue.get("labels", []):
            name = label.get("name", "") if isinstance(label, dict) else str(label)
            if name:
                freq[name] = freq.get(name, 0) + 1
    suggested = sorted(freq, key=lambda k: -freq[k])[:5]
    return {"frequency": freq, "suggested": suggested}


def extract_assignee_patterns(issues: list[dict]) -> dict:
    """Return assignee frequency map and top-5 suggested assignees."""
    freq: dict[str, int] = {}
    for issue in issues:
        for a in issue.get("assignees", []):
            login = a.get("login", "") if isinstance(a, dict) else str(a)
            if login:
                freq[login] = freq.get(login, 0) + 1
    suggested = sorted(freq, key=lambda k: -freq[k])[:5]
    return {"frequency": freq, "suggested": suggested}


def _strip_code_blocks(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def extract_body_structure(issues: list[dict]) -> dict:
    """Detect ## Heading sections across issue bodies. Returns occurrence ratio per section."""
    section_counts: dict[str, int] = {}
    total = len(issues)
    if total == 0:
        return {}
    for issue in issues:
        body = _strip_code_blocks(issue.get("body") or "")
        seen = set()
        for line in body.splitlines():
            m = re.match(r"^(#{1,3} .+)", line.strip())
            if m:
                heading = m.group(1).strip()
                if heading not in seen:
                    section_counts[heading] = section_counts.get(heading, 0) + 1
                    seen.add(heading)
    return {k: round(v / total, 2) for k, v in section_counts.items()}


def extract_title_prefixes(issues: list[dict]) -> list[str]:
    """Return top-5 first-word prefixes from issue titles by frequency."""
    freq: dict[str, int] = {}
    for issue in issues:
        title = issue.get("title", "")
        first = title.split()[0] if title.split() else ""
        if first:
            freq[first] = freq.get(first, 0) + 1
    return sorted(freq, key=lambda k: -freq[k])[:5]


def process_snapshot(
    issues: list[dict],
    labels: list[dict],
    members: list[dict],
    repo: str,
) -> dict:
    """Assemble the full analyzer_snapshot.json dict. Pure function."""
    lp = extract_label_patterns(issues)
    ap = extract_assignee_patterns(issues)
    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "issues": {
            "total_open": sum(1 for i in issues if i.get("state") == "open"),
            "total_sampled": len(issues),
            "label_frequency": lp["frequency"],
            "assignee_frequency": ap["frequency"],
            "title_prefixes": extract_title_prefixes(issues),
            "avg_body_length": (
                int(sum(len(i.get("body") or "") for i in issues) / len(issues))
                if issues else 0
            ),
            "body_sections": extract_body_structure(issues),
        },
        "labels": [
            {"name": l.get("name", ""), "color": l.get("color", ""), "description": l.get("description", "")}
            for l in labels
        ],
        "members": [
            {"login": m.get("login", ""), "issues_assigned": ap["frequency"].get(m.get("login", ""), 0)}
            for m in members
        ],
        "templates": {
            "most_common_sections": [
                k for k, v in sorted(extract_body_structure(issues).items(), key=lambda x: -x[1])[:3]
            ],
            "suggested_labels": lp["suggested"],
            "suggested_assignees": ap["suggested"],
        },
    }


# ── I/O helpers ────────────────────────────────────────────────────────────

def load_snapshot(root: Path) -> dict | None:
    """Read hub_agents/analyzer_snapshot.json. Return None if missing or corrupt."""
    path = root / "hub_agents" / "analyzer_snapshot.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_snapshot(root: Path, snapshot: dict) -> Path:
    """Atomically write snapshot via .tmp → rename."""
    target = root / "hub_agents" / "analyzer_snapshot.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    tmp.replace(target)
    return target


def snapshot_age_hours(snapshot: dict) -> float:
    """Return hours since snapshot['analyzed_at']. Return inf if missing."""
    try:
        analyzed_at = datetime.fromisoformat(snapshot["analyzed_at"])
        now = datetime.now(timezone.utc)
        delta = now - analyzed_at
        return delta.total_seconds() / 3600
    except (KeyError, ValueError):
        return float("inf")


def summarize_for_prompt(snapshot: dict | None) -> str:
    """Compact one-liner for prompt injection. Returns '' if snapshot None/malformed."""
    if not snapshot:
        return ""
    try:
        issues = snapshot.get("issues", {})
        templates = snapshot.get("templates", {})
        labels = " ".join(
            f"{k}({v})" for k, v in list(issues.get("label_frequency", {}).items())[:3]
        )
        assignees = " ".join(templates.get("suggested_assignees", [])[:3])
        sections = " ".join(
            f"{k}({int(v*100)}%)"
            for k, v in list(snapshot.get("issues", {}).get("body_sections", {}).items())[:2]
        )
        prefixes = " ".join(issues.get("title_prefixes", [])[:3])
        parts = []
        if labels:
            parts.append(f"labels: {labels}")
        if assignees:
            parts.append(f"assignees: {assignees}")
        if sections:
            parts.append(f"sections: {sections}")
        if prefixes:
            parts.append(f"prefixes: {prefixes}")
        return "[analyzer] " + " • ".join(parts) if parts else ""
    except Exception:  # noqa: BLE001
        return ""
