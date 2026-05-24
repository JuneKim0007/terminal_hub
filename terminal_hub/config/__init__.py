"""Configuration: workspace config, constants, env, namespace.

Re-exports the public surface so callers can write
`from terminal_hub.config import load_config, COMMAND_NAMESPACE` etc.
"""
from terminal_hub.config.constants import (
    ANALYSIS_BATCH_SIZE,
    ANALYSIS_BATCH_SIZE_MAX,
    ANALYSIS_BATCH_SIZE_MIN,
    COVERAGE_THRESHOLD,
    FILE_TREE_TTL,
    ISSUES_SYNC_TTL,
    MODEL_HAIKU,
    MODEL_OPUS,
    MODEL_SONNET,
    SECONDS_PER_HOUR,
    VALID_MODELS,
)
from terminal_hub.config.env_store import _ensure_gitignored, read_env, write_env
from terminal_hub.config.namespace import COMMAND_NAMESPACE
from terminal_hub.config.settings import (
    WorkspaceMode,
    load_config,
    read_preference,
    save_config,
    write_preference,
)

__all__ = [
    # settings
    "WorkspaceMode",
    "load_config",
    "save_config",
    "read_preference",
    "write_preference",
    # constants
    "ANALYSIS_BATCH_SIZE",
    "ANALYSIS_BATCH_SIZE_MAX",
    "ANALYSIS_BATCH_SIZE_MIN",
    "COVERAGE_THRESHOLD",
    "FILE_TREE_TTL",
    "ISSUES_SYNC_TTL",
    "MODEL_HAIKU",
    "MODEL_OPUS",
    "MODEL_SONNET",
    "SECONDS_PER_HOUR",
    "VALID_MODELS",
    # env
    "read_env",
    "write_env",
    "_ensure_gitignored",
    # namespace
    "COMMAND_NAMESPACE",
]
