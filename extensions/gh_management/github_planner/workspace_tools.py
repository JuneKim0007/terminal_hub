"""Workspace tools for gh_implementation — integrated session setup.

This module provides _do_load_implementation_context, which is used by
pre_implementation() to load repo context, project docs, active issue,
and design refs in a single call.

Full implementation lives in issue #218. This stub exists so that
pre_implementation() can import cleanly and tests can patch the function.
"""
from __future__ import annotations

from pathlib import Path


def _do_load_implementation_context(
    project_root: str,
    issue_slug: str,
    lookup_design_refs: bool = True,
) -> dict:
    """Load implementation context: repo confirm, project docs, active issue, design refs.

    Returns a dict with keys:
        repo_confirmed, project_summary, issue_content, design_sections,
        has_agent_workflow, context_ready

    Raises NotImplementedError — full implementation in issue #218.
    """
    raise NotImplementedError(
        "_do_load_implementation_context is not yet implemented — see issue #218. "
        "Use the individual MCP tools (confirm_session_repo, load_project_docs, "
        "load_active_issue, lookup_feature_section) until #218 lands."
    )
