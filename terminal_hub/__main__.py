import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="terminal-hub",
        description="GitHub issue tracking and project context management for Claude Code.",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("install", help="Register terminal-hub in ~/.claude.json (run once)")
    sub.add_parser("verify", help="Check that terminal-hub is registered in ~/.claude.json")

    args = parser.parse_args()

    if args.command == "install":
        from terminal_hub.install import run_install
        run_install()
    elif args.command == "verify":
        from terminal_hub.install import run_verify
        run_verify()
    else:
        # Default: MCP server mode (no subcommand = stdio)
        from terminal_hub.server import create_server
        server = create_server()
        server.run()


if __name__ == "__main__":
    main()
