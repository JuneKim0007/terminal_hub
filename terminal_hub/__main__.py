from terminal_hub.server import create_server


def main() -> None:
    """MCP server entry point. Always starts immediately — no blocking prompts."""
    server = create_server()
    server.run()


def setup() -> None:
    """Interactive workspace setup. Run once per project: terminal-hub setup"""
    pass  # Implemented in Chunk 5


if __name__ == "__main__":
    main()
