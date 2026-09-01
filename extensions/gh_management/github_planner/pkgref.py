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


def _resolve_root():
    """The active workspace root, paired with a needs_init response or None.

    ``root, err = _resolve_root()`` / ``if err: return err`` is the opening of
    every workspace-touching tool. Stating it once means a new precondition is
    added here rather than in the 34 places that used to spell it out.

    Goes through _pkg() for the same reason _pkg() itself exists: the test suite
    patches ``…github_planner.get_workspace_root`` and ``…ensure_initialized``,
    and a direct import would bind past those patches.
    """
    pkg = _pkg()
    root = pkg.get_workspace_root()
    return root, pkg.ensure_initialized(root)
