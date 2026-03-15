"""GitHub token resolution.

Resolution order:
  1. GITHUB_TOKEN environment variable (explicit)
  2. `gh auth token` (GitHub CLI — if installed and authenticated)
  3. None — Claude receives a suggestion covering both options
"""
import os
import subprocess
from enum import Enum


class TokenSource(Enum):
    ENV = "env"
    GH_CLI = "gh_cli"
    NONE = "none"

    def suggestion(self) -> str:
        if self == TokenSource.NONE:
            return (
                "No GitHub token found. Provide one of:\n"
                "  1. Set GITHUB_TOKEN in your MCP config env.\n"
                "     Generate a token at https://github.com/settings/tokens (scope: repo)\n"
                "  2. Install the GitHub CLI and run: gh auth login\n"
                "     terminal_hub will use it automatically."
            )
        return ""


def resolve_token() -> tuple[str | None, TokenSource]:
    """Return (token, source). Token is None if no auth is available."""
    # 1. Explicit env var
    if token := os.environ.get("GITHUB_TOKEN"):
        return token, TokenSource.ENV

    # 2. GitHub CLI
    try:
        token = subprocess.check_output(
            ["gh", "auth", "token"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if token:
            return token, TokenSource.GH_CLI
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return None, TokenSource.NONE
