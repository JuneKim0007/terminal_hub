"""GitHub token resolution.

Resolution order:
  1. GITHUB_TOKEN environment variable (explicit)
  2. `gh auth token` (GitHub CLI — if installed and authenticated)
  3. None — Claude presents login options to the user in conversation
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
                "No GitHub authentication found. "
                "Call check_auth to present login options to the user."
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


def get_auth_options() -> list[dict]:
    """Return the two login options Claude presents to the user when no auth is found."""
    return [
        {
            "value": "gh_cli",
            "label": "Login with GitHub CLI (recommended)",
            "instructions": (
                "Run this in your terminal:\n"
                "  gh auth login\n"
                "Follow the prompts to authenticate via browser or SSH key. "
                "When done, come back and I will verify it worked."
            ),
            "next_step": "Call verify_auth to confirm the login succeeded.",
        },
        {
            "value": "token",
            "label": "Use a Personal Access Token",
            "instructions": (
                "1. Go to https://github.com/settings/tokens\n"
                "2. Click 'Generate new token (classic)'\n"
                "3. Select the 'repo' scope\n"
                "4. Copy the token and add it to your MCP config:\n"
                '   "env": { "GITHUB_TOKEN": "your_token_here" }\n'
                "5. Restart Claude Code to apply the change."
            ),
            "next_step": "Restart Claude Code after setting GITHUB_TOKEN in your MCP config.",
        },
    ]


def verify_gh_cli_auth() -> tuple[bool, str]:
    """Check if gh CLI is currently authenticated. Returns (success, message)."""
    try:
        token = subprocess.check_output(
            ["gh", "auth", "token"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if token:
            return True, "GitHub CLI authentication verified successfully."
        return False, "gh CLI is installed but not authenticated. Run: gh auth login"
    except FileNotFoundError:
        return False, "GitHub CLI (gh) is not installed. Install it from https://cli.github.com"
    except subprocess.CalledProcessError:
        return False, "gh CLI is installed but not authenticated. Run: gh auth login"
