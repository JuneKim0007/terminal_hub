from mcp.server.fastmcp import FastMCP

from terminal_hub.prompts import TERMINAL_HUB_INSTRUCTIONS


def create_server() -> FastMCP:
    mcp = FastMCP("terminal-hub")

    @mcp.prompt()
    def terminal_hub_instructions() -> str:
        return TERMINAL_HUB_INSTRUCTIONS

    return mcp
