"""Whether a project has been initialised for terminal-hub.

``hub_agents/`` is terminal-hub's own directory and ``terminal-hub://`` is its
own URI scheme, so deciding "is this workspace set up" is core policy. It lived
in the github_planner plugin, which meant the host imported a plugin to answer a
question about itself (R16).
"""
from pathlib import Path

#: Guidance URI returned alongside a needs_init response.
G_INIT = "terminal-hub://workflow/init"

_NEEDS_INIT_MESSAGE = (
    "This project hasn't been set up with terminal-hub yet. "
    "Ask the user: would they like GitHub integration? If yes, what is their repo (owner/repo format)? "
    "Then call setup_workspace to initialise."
)


def hub_agents_dir(root: Path) -> Path:
    """The terminal-hub state directory for a project."""
    return root / "hub_agents"


def is_initialized(root: Path) -> bool:
    """True when the project has a hub_agents/ directory."""
    return hub_agents_dir(root).exists()


def ensure_initialized(root: Path) -> dict | None:
    """Return a needs_init response if hub_agents/ is absent, else None."""
    if is_initialized(root):
        return None
    return {
        "status": "needs_init",
        "message": _NEEDS_INIT_MESSAGE,
        "_guidance": G_INIT,
    }
