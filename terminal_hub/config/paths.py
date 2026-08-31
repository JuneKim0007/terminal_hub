"""Install-tree paths.

These locate files *inside the terminal-hub installation* — not the user's
project, which ``terminal_hub.workspace`` resolves. Computing them once here
keeps the ``parent`` count out of call sites, where it silently depends on how
deep in the package the caller happens to sit.
"""
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent
EXTENSIONS_DIR = REPO_ROOT / "extensions"
BUILTIN_COMMANDS_DIR = EXTENSIONS_DIR / "builtin"

__all__ = ["PACKAGE_ROOT", "REPO_ROOT", "EXTENSIONS_DIR", "BUILTIN_COMMANDS_DIR"]
