"""Command-line surface for `terminal-hub` — install and verify subcommands.

The `__main__` entry point lives at `terminal_hub/__main__.py` and
dispatches into `cli.install` for setup/verification work.
"""
from terminal_hub.cli.install import run_install, run_verify

__all__ = ["run_install", "run_verify"]
