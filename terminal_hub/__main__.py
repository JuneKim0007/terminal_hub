from terminal_hub.server import create_server


def main() -> None:
    """MCP server entry point. Starts immediately — Claude handles workspace setup in conversation."""
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
