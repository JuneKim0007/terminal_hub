"""GitHub REST API client using httpx.

All endpoint paths come from hub_commands.json via commands.endpoint().
All error messages come from error_msg.json via errors.msg().
"""
import base64
import json
from pathlib import Path
from types import TracebackType

import httpx

from extensions.gh_management.github_planner.commands import endpoint
from terminal_hub.errors import msg

_LABELS_FILE = Path(__file__).parent / "labels.json"

BASE_URL = "https://api.github.com"


def load_default_labels() -> list[dict]:
    """Return the list of default label definitions from labels.json."""
    try:
        return json.loads(_LABELS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


# ── Error type ────────────────────────────────────────────────────────────────

class GitHubError(Exception):
    """Raised when a GitHub API call fails."""

    def __init__(self, message: str, error_code: str = "github_error") -> None:
        super().__init__(message)
        self.error_code = error_code

    def to_dict(self) -> dict:
        return {
            "error": self.error_code,
            "message": str(self),
        }


# ── Error mapping ─────────────────────────────────────────────────────────────

def parse_error(status_code: int, body: str) -> dict:
    """Map an HTTP status code to a structured error dict."""
    if status_code == 401:
        return {"error": "auth_failed",       "message": msg("auth_failed")}
    if status_code == 403:
        return {"error": "permission_denied", "message": msg("permission_denied")}
    if status_code == 404:
        return {"error": "repo_not_found",    "message": msg("repo_not_found")}
    if status_code == 422:
        return {"error": "validation_failed", "message": msg("validation_failed", detail=body)}
    if status_code == 429:
        return {"error": "rate_limited",      "message": msg("rate_limited")}
    return {"error": "github_error", "message": msg("github_error", status_code=str(status_code), detail=body)}


# ── Client ────────────────────────────────────────────────────────────────────

class GitHubClient:

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

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._client.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def _url(self, section: str, name: str, **kwargs: str) -> tuple[str, str]:
        """Return (method, full_url) for a named command."""
        method, path = endpoint(section, name)
        return method, BASE_URL + path.format(repo=self.repo, **kwargs)

    def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str],
        assignees: list[str],
    ) -> dict:
        """Create a GitHub issue. Returns response JSON on success. Raises GitHubError on failure."""
        _, url = self._url("github", "create_issue")
        payload = {"title": title, "body": body, "labels": labels, "assignees": assignees}

        try:
            response = self._client.post(url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError:
            info = parse_error(response.status_code, response.text)
            raise GitHubError(info["message"], error_code=info["error"])
        except httpx.ConnectError as exc:
            raise GitHubError(msg("network_error", detail=str(exc)), error_code="network_error")
        except httpx.TimeoutException:
            raise GitHubError(msg("timeout"), error_code="timeout")

        return response.json()

    def list_labels(self) -> list[dict]:
        """List all labels from the repo as raw dicts."""
        _, url = self._url("github", "list_labels")
        labels: list[dict] = []
        page = 1
        while True:
            try:
                resp = self._client.get(url, params={"per_page": 100, "page": page})
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                return labels
            data = resp.json()
            if not data:
                break
            labels.extend(data)
            if len(data) < 100:
                break
            page += 1
        return labels

    def list_issues(self, state: str = "all", per_page: int = 50, limit: int | None = None) -> list[dict]:
        """List issues from the repo."""
        _, url = self._url("github", "list_issues")
        page_size = limit if limit is not None else per_page
        resp = self._client.get(url, params={"state": state, "per_page": page_size})
        resp.raise_for_status()
        return resp.json()

    def list_issues_all(self, state: str = "open") -> list[dict]:
        """List all issues with pagination (up to 500)."""
        _, url = self._url("github", "list_issues")
        issues: list[dict] = []
        page = 1
        while len(issues) < 500:
            try:
                resp = self._client.get(url, params={"state": state, "per_page": 100, "page": page})
                resp.raise_for_status()
            except Exception:
                break
            data = resp.json()
            if not data:
                break
            issues.extend(data)
            if len(data) < 100:
                break
            page += 1
        return issues

    def get_issue(self, number: int) -> dict:
        """Fetch a single issue by number."""
        _, base_url = self._url("github", "list_issues")
        url = base_url.rstrip("/") + f"/{number}"
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.json()

    def list_collaborators(self) -> list[dict]:
        """List repo collaborators."""
        url = BASE_URL + f"/repos/{self.repo}/collaborators"
        resp = self._client.get(url, params={"per_page": 100})
        if resp.status_code == 403:
            return []  # No collaborator access — return empty gracefully
        resp.raise_for_status()
        return resp.json()

    def get_labels(self) -> set[str]:
        """Return the set of label names that exist in the repo."""
        _, url = self._url("github", "list_labels")
        names: set[str] = set()
        page = 1
        while True:
            try:
                resp = self._client.get(url, params={"per_page": 100, "page": page})
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                return names
            data = resp.json()
            if not data:
                break
            names.update(item["name"] for item in data)
            if len(data) < 100:
                break
            page += 1
        return names

    def close_issue(self, number: int, comment: str | None = None) -> dict:
        """Close a GitHub issue. Optionally post a comment first."""
        if comment:
            comment_url = BASE_URL + f"/repos/{self.repo}/issues/{number}/comments"
            self._client.post(comment_url, json={"body": comment})
        url = BASE_URL + f"/repos/{self.repo}/issues/{number}"
        resp = self._client.patch(url, json={"state": "closed"})
        if resp.status_code not in (200, 201):
            raise GitHubError(f"Failed to close issue #{number}: {resp.status_code}")
        return resp.json()

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        """Create a label. If it already exists (422), fetch and return the existing one."""
        url = BASE_URL + f"/repos/{self.repo}/labels"
        resp = self._client.post(url, json={"name": name, "color": color.lstrip("#"), "description": description})
        if resp.status_code in (200, 201):
            return resp.json()
        if resp.status_code == 422:
            # Label already exists — fetch it
            existing = self._client.get(url + f"/{name}")
            if existing.status_code == 200:
                return existing.json()
        raise GitHubError(f"Failed to create label '{name}': {resp.status_code}")

    def update_label(self, name: str, new_description: str) -> dict:
        """Update a label's description (idempotent — no error if label not found)."""
        url = BASE_URL + f"/repos/{self.repo}/labels/{name}"
        resp = self._client.patch(url, json={"description": new_description})
        if resp.status_code in (200, 201):
            return resp.json()
        raise GitHubError(f"Failed to update label '{name}': {resp.status_code}")

    def create_milestone(self, title: str, description: str = "", due_on: str | None = None) -> dict:
        """Create a milestone. If title already exists (422), fetch and return the existing one."""
        url = BASE_URL + f"/repos/{self.repo}/milestones"
        payload: dict = {"title": title, "description": description}
        if due_on:
            payload["due_on"] = due_on
        resp = self._client.post(url, json=payload)
        if resp.status_code in (200, 201):
            return resp.json()
        if resp.status_code == 422:
            # Milestone likely already exists — find it by title
            existing = self._client.get(url, params={"state": "open", "per_page": 100})
            if existing.status_code == 200:
                for m in existing.json():
                    if m["title"] == title:
                        return m
        raise GitHubError(f"Failed to create milestone '{title}': {resp.status_code}")

    def list_milestones(self, state: str = "open") -> list[dict]:
        """Return all milestones for the repo."""
        url = BASE_URL + f"/repos/{self.repo}/milestones"
        resp = self._client.get(url, params={"state": state, "per_page": 100})
        if resp.status_code != 200:
            raise GitHubError(f"Failed to list milestones: {resp.status_code}")
        return resp.json()

    def update_issue_milestone(self, issue_number: int, milestone_number: int) -> dict:
        """Assign a milestone to an existing GitHub issue."""
        url = BASE_URL + f"/repos/{self.repo}/issues/{issue_number}"
        resp = self._client.patch(url, json={"milestone": milestone_number})
        if resp.status_code not in (200, 201):
            raise GitHubError(f"Failed to assign milestone to #{issue_number}: {resp.status_code}")
        return resp.json()

    def list_repo_tree(self, branch: str = "HEAD") -> list[dict]:
        """Return [{path, size}] for every blob in the repo tree."""
        url = BASE_URL + f"/repos/{self.repo}/git/trees/{branch}?recursive=1"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            info = parse_error(resp.status_code, resp.text)
            raise GitHubError(info["message"], error_code=info["error"])
        except httpx.ConnectError as exc:
            raise GitHubError(msg("network_error", detail=str(exc)), error_code="network_error")
        except httpx.TimeoutException:
            raise GitHubError(msg("timeout"), error_code="timeout")

        return [
            {"path": item["path"], "size": item.get("size", 0), "sha": item.get("sha", "")}
            for item in resp.json().get("tree", [])
            if item.get("type") == "blob"
        ]

    def get_file_content(self, path: str) -> str:
        """Fetch raw UTF-8 content of a single file.
        Raises GitHubError with error_code='binary_file' or 'file_too_large'."""
        url = BASE_URL + f"/repos/{self.repo}/contents/{path}"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            info = parse_error(resp.status_code, resp.text)
            raise GitHubError(info["message"], error_code=info["error"])
        except httpx.ConnectError as exc:
            raise GitHubError(msg("network_error", detail=str(exc)), error_code="network_error")
        except httpx.TimeoutException:
            raise GitHubError(msg("timeout"), error_code="timeout")

        data = resp.json()
        if data.get("encoding") != "base64":
            raise GitHubError(f"Unsupported encoding for {path}", error_code="binary_file")

        raw_bytes = base64.b64decode(data.get("content", ""))
        if len(raw_bytes) > 100 * 1024:
            raise GitHubError(
                f"File {path} is too large ({len(raw_bytes)} bytes)", error_code="file_too_large"
            )
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise GitHubError(f"File {path} is binary or non-UTF-8", error_code="binary_file")

    def get_authenticated_user(self) -> dict:
        """Return the authenticated user's login and name."""
        resp = self._client.get(BASE_URL + "/user")
        resp.raise_for_status()
        return resp.json()

    def ensure_labels(self, labels: list[str]) -> str | None:
        """Ensure all requested labels exist, creating missing ones from labels.json.

        Returns None on success, or an error string when any label could not be
        found or created — caller returns this to Claude to handle directly.
        """
        if not labels:
            return None

        existing = self.get_labels()
        missing = [label for label in labels if label not in existing]
        if not missing:
            return None

        default_defs = {d["name"]: d for d in load_default_labels()}
        failed: list[str] = []

        for name in missing:
            defn = default_defs.get(name)
            if defn:
                try:
                    self.create_label(name, defn["color"], defn.get("description", ""))
                except GitHubError:
                    failed.append(name)
            else:
                failed.append(name)

        if failed:
            return msg("label_bootstrap_failed", detail=", ".join(failed))
        return None


def create_user_repo(token: str, name: str, description: str, private: bool) -> dict:
    """Create a new GitHub repo under the authenticated user. Returns response JSON.

    Raises GitHubError on API failure.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"name": name, "description": description, "private": private, "auto_init": True}
    try:
        resp = httpx.post(BASE_URL + "/user/repos", json=payload, headers=headers, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        info = parse_error(resp.status_code, resp.text)
        raise GitHubError(info["message"], error_code=info["error"])
    except httpx.ConnectError as exc:
        raise GitHubError(msg("network_error", detail=str(exc)), error_code="network_error")
    except httpx.TimeoutException:
        raise GitHubError(msg("timeout"), error_code="timeout")
    return resp.json()
