"""Curses-based interactive issue browser for terminal-hub.

Invoked by `terminal-hub list`. Assumes a proper Unix TTY (Claude Code terminal).

Keyboard controls:
    ↑ / k       move up
    ↓ / j       move down
    ↵ / space   toggle expand/collapse
    q / Q       quit
"""
from __future__ import annotations

import curses
import sys
from typing import Any

from terminal_hub.storage import list_issue_files
from terminal_hub.workspace import resolve_workspace_root


# ── Pure formatting helpers (fully testable without curses) ───────────────────

def truncate(s: str, width: int) -> str:
    """Truncate *s* to *width* characters, appending '…' if cut."""
    if width <= 0:
        return ""
    if len(s) <= width:
        return s
    if width == 1:
        return "…"
    return s[: width - 1] + "…"


def format_number(issue: dict[str, Any]) -> str:
    """Return '#N' or 'local' when no issue_number is present."""
    num = issue.get("issue_number")
    return f"#{num}" if num is not None else "local"


def format_labels(labels: list[str]) -> str:
    """Format up to 2 labels as '[a] [b]', with '+N' overflow indicator."""
    if not labels:
        return ""
    shown = labels[:2]
    rest = len(labels) - 2
    parts = [f"[{lbl}]" for lbl in shown]
    if rest > 0:
        parts.append(f"+{rest}")
    return " ".join(parts)


def format_detail_lines(issue: dict[str, Any]) -> list[tuple[str, str]]:
    """Return ordered (field, value) pairs for the expanded detail view.

    Fields with no meaningful value are omitted entirely:
    - assignees: skipped if empty or None
    - labels:    skipped if empty or None
    - github_url: skipped if None
    - created_at: skipped if None
    Status and File are always included.
    """
    lines: list[tuple[str, str]] = []

    status = issue.get("status") or "—"
    lines.append(("Status", status))

    created = issue.get("created_at")
    if created:
        lines.append(("Created", str(created)))

    assignees = issue.get("assignees") or []
    if assignees:
        lines.append(("Assignees", ", ".join(assignees)))

    labels = issue.get("labels") or []
    if labels:
        lines.append(("Labels", ", ".join(labels)))

    url = issue.get("github_url")
    if url:
        lines.append(("URL", url))

    lines.append(("File", issue.get("file", "")))

    return lines


# ── Curses rendering ──────────────────────────────────────────────────────────

_KEY_UP    = {curses.KEY_UP, ord("k")}
_KEY_DOWN  = {curses.KEY_DOWN, ord("j")}
_KEY_OPEN  = {curses.KEY_RIGHT, ord("\n"), ord(" ")}
_KEY_QUIT  = {ord("q"), ord("Q")}


class IssueBrowser:
    """Keyboard-navigable curses issue list with inline expand/collapse."""

    def __init__(self, stdscr: "curses.window", issues: list[dict[str, Any]]) -> None:
        self._scr = stdscr
        self._issues = issues
        self._cursor = 0
        self._expanded: set[int] = set()

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw(self) -> None:  # pragma: no cover
        self._scr.erase()
        h, w = self._scr.getmaxyx()

        # Header
        header = f" terminal-hub · {len(self._issues)} issue{'s' if len(self._issues) != 1 else ''}"
        self._scr.addstr(0, 0, header[:w], curses.A_BOLD)
        self._scr.addstr(1, 0, "─" * (w - 1))

        row = 2
        for idx, issue in enumerate(self._issues):
            if row >= h - 2:
                break
            selected = idx == self._cursor
            expanded = idx in self._expanded

            arrow = "▼" if expanded else "▶"
            prefix = f" {arrow}  " if selected else "    "
            num = format_number(issue)
            labels_str = format_labels(issue.get("labels") or [])

            # calculate space: prefix(4) + num(~4) + space(1) + title + space(2) + labels
            num_w = len(num)
            labels_w = len(labels_str)
            title_w = max(0, w - len(prefix) - num_w - 1 - 2 - labels_w - 1)
            title = truncate(issue.get("title", ""), title_w)

            line = f"{prefix}{num}  {title:<{title_w}}  {labels_str}"

            attr = curses.A_REVERSE if selected else curses.A_NORMAL
            try:
                self._scr.addstr(row, 0, line[:w - 1], attr)
            except curses.error:
                pass
            row += 1

            if expanded:
                detail_lines = format_detail_lines(issue)
                key_w = max((len(k) for k, _ in detail_lines), default=6)
                for field, value in detail_lines:
                    if row >= h - 2:
                        break
                    detail = f"       {field:<{key_w}}  {value}"
                    try:
                        self._scr.addstr(row, 0, detail[:w - 1])
                    except curses.error:
                        pass
                    row += 1
                row += 1  # blank line after expanded block

        # Footer
        footer = " ↑↓/jk navigate   ↵/space toggle   q quit"
        try:
            self._scr.addstr(h - 1, 0, footer[:w - 1], curses.A_DIM)
        except curses.error:
            pass

        self._scr.refresh()

    # ── Event loop ────────────────────────────────────────────────────────────

    def run(self) -> None:  # pragma: no cover
        curses.curs_set(0)
        while True:
            self._draw()
            key = self._scr.getch()

            if key in _KEY_QUIT:
                break
            elif key in _KEY_UP:
                self._cursor = max(0, self._cursor - 1)
            elif key in _KEY_DOWN:
                self._cursor = min(len(self._issues) - 1, self._cursor + 1)
            elif key in _KEY_OPEN:
                if self._cursor in self._expanded:
                    self._expanded.discard(self._cursor)
                else:
                    self._expanded.add(self._cursor)


# ── Entry point ───────────────────────────────────────────────────────────────

def run_browser() -> None:
    """Load issues from workspace and launch the curses browser."""
    root = resolve_workspace_root()
    issues = list_issue_files(root)

    if not issues:
        print("No issues found in hub_agents/issues/")
        return

    def _main(stdscr: "curses.window") -> None:  # pragma: no cover
        IssueBrowser(stdscr, issues).run()

    curses.wrapper(_main)
