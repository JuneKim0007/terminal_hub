"""gh_implementation extension — stub.

Full implementation tracked across issues #123–#132.
Registers a minimal set of MCP tools; expand as features are built.
"""
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register gh_implementation tools on the shared MCP server."""

    @mcp.tool()
    def get_implementation_session() -> dict:
        """Return current session-scoped implementation flags.

        Flags (all default True unless changed by user this session):
          close_automatically_on_gh:    push + close issue on GitHub after user accepts changes
          delete_local_issue_on_gh:     delete local hub_agents/issues/<slug>.md after GH close
        """
        # TODO (#128): persist session flags in-memory; expose via /th:gh-implementation/session-knowledge
        return {
            "close_automatically_on_gh": True,
            "delete_local_issue_on_gh": True,
            "_display": (
                "Implementation session flags (defaults — change by asking or via /th:gh-implementation/session-knowledge):\n"
                "  close_automatically_on_gh:  true  — push + close issue on GitHub after acceptance\n"
                "  delete_local_issue_on_gh:   true  — delete local issue file after GH close"
            ),
        }
