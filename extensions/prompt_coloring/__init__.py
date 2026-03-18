"""prompt_coloring extension — styled interactive prompts for terminal-hub.

Renders prompts with markdown bold/emoji so Claude Code's UI highlights them.

Tool: format_prompt(question, options, style)
Returns _display — print it verbatim to show the styled prompt.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

# ── Style map: (emoji prefix, markdown wrapper) ───────────────────────────────
# Claude Code renders markdown, not raw ANSI — use bold + emoji.
_STYLES: dict[str, tuple[str, str]] = {
    "question": ("❓", "**"),   # bold question
    "confirm":  ("✅", "**"),   # bold confirm / success
    "warning":  ("⚠️", "**"),   # bold warning
    "switch":   ("→", "**"),    # bold mode switch
    "error":    ("❌", "**"),   # bold error
}

_DEFAULT_STYLE = "question"


def _do_format_prompt(
    question: str,
    options: list[str] | None = None,
    style: str = "question",
) -> dict:
    icon, wrap = _STYLES.get(style, _STYLES[_DEFAULT_STYLE])

    q_line = f"{icon} {wrap}{question}{wrap}"

    if options:
        opts_str = " / ".join(options)
        display = f"{q_line} *({opts_str})*"
    else:
        display = q_line

    return {"_display": display, "style": style, "question": question, "options": options or []}


def register(mcp: FastMCP) -> None:
    """Register prompt_coloring tools on the shared MCP server."""

    @mcp.tool()
    def format_prompt(
        question: str,
        options: list[str] | None = None,
        style: str = "question",
    ) -> dict:
        """Format an interactive prompt with an emoji icon and bold markdown.

        Print _display verbatim to show the styled prompt.

        style: 'question' (❓ bold) | 'confirm' (✅ bold) | 'warning' (⚠️ bold)
               'switch'   (→ bold)  | 'error'   (❌ bold)
        options: list of choices shown as "(yes / no / cancel)"

        Example:
          format_prompt("Accept these changes?", ["yes", "review more", "cancel"])
          → ❓ **Accept these changes?** *(yes / review more / cancel)*
        """
        return _do_format_prompt(question, options, style)
