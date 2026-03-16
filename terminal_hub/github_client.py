"""GitHub REST API client using httpx.

Errors are always structured with a suggestion so Claude can explain
exactly what the user needs to do to fix the problem.
"""
import json
from pathlib import Path

import httpx

_LABELS_FILE = Path(__file__).parent / "labels.json"


def _load_default_labels() -> list[dict]:
    try:
        return json.loads(_LABELS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return []


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

    def get_labels(self) -> set[str]:
        """Return the set of label names that exist in the repo."""
        url = f"{self.BASE_URL}/repos/{self.repo}/labels"
        names: set[str] = set()
        page = 1
        while True:
            try:
                resp = self._client.get(url, params={"per_page": 100, "page": page})
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                return names  # best-effort; caller decides what to do on error
            data = resp.json()
            if not data:
                break
            names.update(item["name"] for item in data)
            if len(data) < 100:
                break
            page += 1
        return names

    def create_label(self, name: str, color: str, description: str) -> bool:
        """Create a label. Returns True on success, False if already exists or on error."""
        url = f"{self.BASE_URL}/repos/{self.repo}/labels"
        try:
            resp = self._client.post(url, json={"name": name, "color": color, "description": description})
            return resp.status_code in (201, 422)  # 422 = already exists
        except httpx.HTTPError:
            return False

    def ensure_labels(self, labels: list[str]) -> str | None:
        """Ensure all requested labels exist, creating missing ones from labels.json.

        Returns None on success, or a short error string if any label could not
        be found or created (so Claude can surface it to the user).
        """
        if not labels:
            return None

        existing = self.get_labels()
        missing = [l for l in labels if l not in existing]
        if not missing:
            return None

        default_defs = {d["name"]: d for d in _load_default_labels()}
        failed: list[str] = []

        for name in missing:
            defn = default_defs.get(name)
            if defn:
                ok = self.create_label(name, defn["color"], defn.get("description", ""))
                if not ok:
                    failed.append(name)
            else:
                failed.append(name)

        if failed:
            return f"Labels not found and could not be created: {', '.join(failed)}"
        return None
