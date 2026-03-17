"""GitHub token resolution.

Resolution order:
  1. GITHUB_TOKEN environment variable (explicit)
  2. `gh auth token` (GitHub CLI — if installed and authenticated)
  3. None — Claude presents login options to the user in conversation
"""
import os
import subprocess
from enum import Enum

# Module-level token cache — resolved once per process, invalidated by verify_gh_cli_auth
_TOKEN_CACHE: dict[str, tuple[str | None, "TokenSource"]] = {}
_TOKEN_CACHE_KEY = "resolved"


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


def resolve_token() -> tuple[str | None, "TokenSource"]:
    """Return (token, source). Token is None if no auth is available.

    Result is cached for the process lifetime. Call invalidate_token_cache()
    after successful auth to force re-resolution.
    """
    if _TOKEN_CACHE_KEY in _TOKEN_CACHE:
        return _TOKEN_CACHE[_TOKEN_CACHE_KEY]

    result = _resolve_token_uncached()
    _TOKEN_CACHE[_TOKEN_CACHE_KEY] = result
    return result


def _resolve_token_uncached() -> tuple[str | None, "TokenSource"]:
    """Resolve token without cache."""
    # 1. Explicit env var
    if token := os.environ.get("GITHUB_TOKEN"):
        return token, TokenSource.ENV

    # 2. GitHub CLI
    try:
        token = subprocess.check_output(
            ["gh", "auth", "token"],
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
        ).strip()
        if token:
            return token, TokenSource.GH_CLI
    except FileNotFoundError:
        pass  # gh not installed — not an error, just unavailable
    except subprocess.CalledProcessError:
        pass  # gh installed but not authenticated

    return None, TokenSource.NONE


def invalidate_token_cache() -> None:
    """Force next resolve_token() call to re-run subprocess.

    Call after verify_gh_cli_auth() succeeds or GITHUB_TOKEN changes.
    """
    _TOKEN_CACHE.clear()


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
    """Check if gh CLI is currently authenticated. Returns (success, message).

    Invalidates the token cache on success so the next tool call picks up the
    fresh token.
    """
    try:
        token = subprocess.check_output(
            ["gh", "auth", "token"],
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
        ).strip()
        if token:
            invalidate_token_cache()
            return True, "GitHub CLI authentication verified successfully."
        return False, "gh CLI is installed but not authenticated. Run: gh auth login"
    except FileNotFoundError:
        return False, "GitHub CLI (gh) is not installed. Install it from https://cli.github.com"
    except subprocess.CalledProcessError:
        return False, "gh CLI is installed but not authenticated. Run: gh auth login"
