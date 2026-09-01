"""Late-bound access to the ``github_planner`` package module.

Domain modules reach shared helpers (``get_workspace_root``,
``ensure_initialized``, ``get_github_client``, …) through this instead of
importing them directly. ``from … import f`` binds at import time, which would
make ``patch("extensions.gh_management.github_planner.f")`` a no-op — and the
suite has roughly 600 such patch sites, so the failure mode is tests passing
against unpatched production code, not tests failing.
"""
import sys

_PKG = "extensions.gh_management.github_planner"


def _pkg():
    """Return the github_planner package module so patches applied by tests are respected."""
    return sys.modules[_PKG]
