"""GitHub REST API client using httpx.

Errors are always structured with a suggestion so Claude can explain
exactly what the user needs to do to fix the problem.
"""
import httpx


# ── Error type ────────────────────────────────────────────────────────────────

class GitHubError(Exception):
    """Raised when a GitHub API call fails.

    Always carries a human-readable suggestion so Claude can guide the user.
    """

    def __init__(self, message: str, error_code: str = "github_error", suggestion: str = "") -> None:
        super().__init__(message)
        self.error_code = error_code
        self.suggestion = suggestion

    def to_dict(self) -> dict:
        return {
            "error": self.error_code,
            "message": str(self),
            "suggestion": self.suggestion,
        }


# ── Error mapping ─────────────────────────────────────────────────────────────

def parse_error(status_code: int, body: str) -> dict:
    """Map an HTTP status code to a structured error dict with a suggestion."""
    if status_code == 401:
        return {
            "error": "auth_failed",
            "message": "GitHub rejected the token.",
            "suggestion": (
                "Your GITHUB_TOKEN is invalid or expired. "
                "Generate a new one at https://github.com/settings/tokens "
                "with the 'repo' scope, then update your MCP config."
            ),
        }
    if status_code == 403:
        return {
            "error": "permission_denied",
            "message": "GitHub denied access.",
            "suggestion": (
                "Your GITHUB_TOKEN may be missing the required scope. "
                "Ensure it has the 'repo' scope at https://github.com/settings/tokens."
            ),
        }
    if status_code == 404:
        return {
            "error": "repo_not_found",
            "message": "The GitHub repository was not found.",
            "suggestion": (
                "Check that GITHUB_REPO is set correctly (format: owner/repo-name) "
                "and that your token has access to it. "
                "You can override it with GITHUB_REPO=owner/repo in your MCP env config."
            ),
        }
    if status_code == 422:
        return {
            "error": "validation_failed",
            "message": f"GitHub rejected the request: {body}",
            "suggestion": (
                "The issue data may be malformed. "
                "Check that labels and assignees exist in the repository."
            ),
        }
    if status_code == 429:
        return {
            "error": "rate_limited",
            "message": "GitHub API rate limit exceeded.",
            "suggestion": "Wait a few minutes and try again. Authenticated requests allow 5000/hour.",
        }
    return {
        "error": "github_error",
        "message": f"GitHub returned status {status_code}: {body}",
        "suggestion": "Check the GitHub status page or try again shortly.",
    }


# ── Client ────────────────────────────────────────────────────────────────────

class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str, repo: str) -> None:
        self.repo = repo
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str],
        assignees: list[str],
    ) -> dict:
        """Create a GitHub issue. Returns response JSON on success.

        Raises GitHubError with a suggestion on any failure so Claude can
        guide the user to fix the problem without manual debugging.
        """
        url = f"{self.BASE_URL}/repos/{self.repo}/issues"
        payload = {"title": title, "body": body, "labels": labels, "assignees": assignees}

        try:
            response = self._client.post(url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError:
            info = parse_error(response.status_code, response.text)
            raise GitHubError(
                info["message"],
                error_code=info["error"],
                suggestion=info["suggestion"],
            )
        except httpx.ConnectError as exc:
            raise GitHubError(
                f"Could not connect to GitHub: {exc}",
                error_code="network_error",
                suggestion=(
                    "Check your internet connection. "
                    "If you are behind a proxy, set HTTPS_PROXY in your environment."
                ),
            )
        except httpx.TimeoutException:
            raise GitHubError(
                "GitHub request timed out.",
                error_code="timeout",
                suggestion="Try again in a moment. If this persists, check your network connection.",
            )

        return response.json()
