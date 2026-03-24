"""plugin_customization — model routing for terminal-hub.

Dispatches named task types to the appropriate Claude model based on
a user-editable plugin_config.json. Lightweight tasks (file_location,
issue_classification, structure_scan) route to Haiku by default; heavier
tasks stay on Sonnet. Users can override any mapping without touching code.

Tools:
  dispatch_task(task_type, prompt, context?)  — call the right model, get structured result
  get_plugin_config()                         — show full routing config
  set_model_for_task(task_type, model)        — update one mapping + persist
  list_task_types()                           — show routing table
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from terminal_hub.constants import MODEL_HAIKU, MODEL_SONNET, MODEL_OPUS, VALID_MODELS
from terminal_hub.workspace import resolve_workspace_root

# ── Paths ─────────────────────────────────────────────────────────────────────

_EXT_DIR = Path(__file__).parent
_DEFAULT_CONFIG_PATH = _EXT_DIR / "plugin_config.json"

_KNOWN_MODELS = set(VALID_MODELS)

# ── Config loading + hot-reload ───────────────────────────────────────────────

_config_cache: dict[str, Any] = {}
_config_mtime: float = 0.0


def _user_config_path() -> Path:
    """Prefer hub_agents override; fall back to extension default."""
    root = resolve_workspace_root()
    user_path = root / "hub_agents" / "extensions" / "plugin_customization" / "plugin_config.json"
    return user_path if user_path.exists() else _DEFAULT_CONFIG_PATH


def _load_config(force: bool = False) -> dict[str, Any]:
    global _config_cache, _config_mtime
    path = _user_config_path()
    mtime = path.stat().st_mtime if path.exists() else 0.0
    if force or mtime != _config_mtime or not _config_cache:
        raw = json.loads(path.read_text()) if path.exists() else {}
        _config_cache = raw
        _config_mtime = mtime
    return _config_cache


def _model_for_task(task_type: str) -> str:
    cfg = _load_config()
    routing = cfg.get("model_routing", {})
    return routing.get("tasks", {}).get(task_type) or routing.get("default", MODEL_SONNET)


def _save_config(cfg: dict[str, Any]) -> None:
    """Persist config to hub_agents override path, creating dirs as needed."""
    root = resolve_workspace_root()
    out = root / "hub_agents" / "extensions" / "plugin_customization" / "plugin_config.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, indent=2))
    _load_config(force=True)


# ── Task type system prompts ───────────────────────────────────────────────────

_SYSTEM_PROMPTS: dict[str, str] = {
    "file_location": (
        "You are a file-finding assistant. Given a query, return ONLY a JSON array of "
        "file paths most likely to be relevant, ranked by relevance (most relevant first). "
        "No explanation, no prose — just the JSON array. Example: "
        '["/src/auth.py", "/tests/test_auth.py"]'
    ),
    "issue_classification": (
        "You are an issue sizing assistant. Classify the given issue as one of: "
        "trivial, small, medium, large. "
        "trivial=single-file no-logic change (chore/docs/refactor only); "
        "small=isolated bug fix or single-focus change; "
        "medium=new capability touching 2-5 files; "
        "large=cross-cutting or new subsystem. "
        'Return ONLY valid JSON: {"size": "small", "reason": "one sentence"}. No prose.'
    ),
    "structure_scan": (
        "You are a project structure analyst. Given a file tree, return ONLY a JSON array "
        "of objects describing each major directory's purpose. "
        'Each object: {"dir": "path/to/dir", "purpose": "one sentence description"}. '
        "Focus on top-level directories and key subdirectories. No prose, just JSON."
    ),
}

_DEFAULT_SYSTEM = (
    "You are a helpful assistant. Return a concise, focused response. "
    "If a JSON format is implied by the task, return only valid JSON."
)


def _do_dispatch_task(
    task_type: str,
    prompt: str,
    context: str | None = None,
) -> dict:
    """Call the model mapped to task_type and return a structured result."""
    try:
        import anthropic  # lazy import — not required for non-routing usage
    except ImportError:
        return {
            "error": "missing_dependency",
            "message": "anthropic package not installed. Run: pip install anthropic",
            "_display": "❌ **dispatch_task failed** — `anthropic` package not installed",
        }

    model = _model_for_task(task_type)
    system = _SYSTEM_PROMPTS.get(task_type, _DEFAULT_SYSTEM)
    full_prompt = f"{context}\n\n{prompt}" if context else prompt

    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": full_prompt}],
        )
        raw = message.content[0].text.strip()
    except Exception as exc:
        return {
            "error": "api_error",
            "message": str(exc),
            "_display": f"❌ **dispatch_task failed** — {exc}",
        }

    # Try to parse JSON result for structured task types
    parsed: Any = raw
    if task_type in _SYSTEM_PROMPTS:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            pass  # return raw string if JSON parse fails

    result: dict[str, Any] = {
        "task_type": task_type,
        "model_used": model,
        "result": parsed,
        "_display": f"✓ **{task_type}** dispatched to `{model}`",
    }

    # Promote well-known keys for convenience
    if task_type == "file_location" and isinstance(parsed, list):
        result["files"] = parsed
    elif task_type == "issue_classification" and isinstance(parsed, dict):
        result["size"] = parsed.get("size")
        result["reason"] = parsed.get("reason")
    elif task_type == "structure_scan" and isinstance(parsed, list):
        result["areas"] = parsed

    return result


def _do_get_plugin_config() -> dict:
    cfg = _load_config()
    routing = cfg.get("model_routing", {})
    default = routing.get("default", MODEL_SONNET)
    tasks = routing.get("tasks", {})

    lines = ["**Model Routing Config**", "", f"default: `{default}`", "", "| Task | Model |", "|------|-------|"]
    for task, model in tasks.items():
        lines.append(f"| {task} | `{model}` |")
    lines.append(f"\n*Config path: `{_user_config_path()}`*")

    return {
        "config": cfg,
        "config_path": str(_user_config_path()),
        "_display": "\n".join(lines),
    }


def _do_set_model_for_task(task_type: str, model: str) -> dict:
    if model not in _KNOWN_MODELS:
        known = ", ".join(f"`{m}`" for m in sorted(_KNOWN_MODELS))
        return {
            "error": "unknown_model",
            "message": f"Unknown model '{model}'. Known models: {known}",
            "_display": f"❌ **Unknown model** `{model}` — valid: {known}",
        }

    cfg = _load_config()
    cfg.setdefault("model_routing", {}).setdefault("tasks", {})[task_type] = model
    _save_config(cfg)

    return {
        "task_type": task_type,
        "model": model,
        "_display": f"✅ **{task_type}** → `{model}` (saved to config)",
    }


def _do_list_task_types() -> dict:
    cfg = _load_config()
    routing = cfg.get("model_routing", {})
    default = routing.get("default", MODEL_SONNET)
    tasks = routing.get("tasks", {})

    lines = [
        "**Task → Model routing**",
        "",
        f"| Task type | Model | Notes |",
        f"|-----------|-------|-------|",
    ]
    for task, model in tasks.items():
        tier = "⚡ fast" if "haiku" in model else ("🧠 smart" if "opus" in model else "")
        lines.append(f"| `{task}` | `{model}` | {tier} |")
    lines.append(f"| *(default)* | `{default}` | fallback for unknown task types |")

    return {
        "task_types": list(tasks.keys()),
        "default_model": default,
        "_display": "\n".join(lines),
    }


# ── Registration ──────────────────────────────────────────────────────────────

def register(mcp: FastMCP) -> None:
    """Register plugin_customization tools on the shared MCP server."""

    @mcp.tool()
    def dispatch_task(
        task_type: str,
        prompt: str,
        context: str | None = None,
    ) -> dict:
        """Dispatch a task to the model configured for that task type.

        Reads plugin_config.json to determine which Claude model handles
        this task_type. Lightweight tasks (file_location, issue_classification,
        structure_scan) route to Haiku by default.

        Returns structured result with task_type, model_used, and result.
        Well-known task types also return convenience keys:
          file_location       → result["files"] = [path, ...]
          issue_classification → result["size"], result["reason"]
          structure_scan      → result["areas"] = [{dir, purpose}, ...]
        """
        return _do_dispatch_task(task_type, prompt, context)

    @mcp.tool()
    def get_plugin_config() -> dict:
        """Return the current model routing config and its file path.

        Shows which model is assigned to each task type and where the
        config file lives (hub_agents override or extension default).
        """
        return _do_get_plugin_config()

    @mcp.tool()
    def set_model_for_task(task_type: str, model: str) -> dict:
        """Assign a specific model to a task type and persist to plugin_config.json.

        model must be one of: claude-haiku-4-5-20251001, claude-sonnet-4-6, claude-opus-4-6
        (see terminal_hub.constants.VALID_MODELS)
        Changes take effect immediately (no server restart needed).
        """
        return _do_set_model_for_task(task_type, model)

    @mcp.tool()
    def list_task_types() -> dict:
        """List all registered task types and their assigned models.

        Shows ⚡ for Haiku (fast/cheap), 🧠 for Opus (powerful), plain for Sonnet.
        """
        return _do_list_task_types()
