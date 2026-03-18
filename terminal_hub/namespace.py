"""Single source of truth for the terminal-hub command namespace.

To rename all slash commands (e.g. /th:... → /myhub:...),
change COMMAND_NAMESPACE here. plugin_loader and install
import this value; no other file needs to change.

Individual plugins may still override this via install_namespace
in their plugin.json — useful when a plugin ships under a
deliberately different prefix.
"""

COMMAND_NAMESPACE = "th"
