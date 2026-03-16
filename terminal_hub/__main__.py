import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="terminal-hub")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("install", help="Add terminal-hub to Claude Code for this project")

    args = parser.parse_args()

    if args.command == "install":
        from terminal_hub.install import run_install
        run_install()
    else:
        # Default: start MCP server (no subcommand = MCP stdio mode)
        from terminal_hub.server import create_server
        server = create_server()
        server.run()


if __name__ == "__main__":
    main()
