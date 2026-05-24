"""Central constants for terminal-hub.

All configurable values live here — TTLs, model names, cache keys, batch sizes.
Import from this module instead of hardcoding literals in implementation code.
"""

# ── Time ──────────────────────────────────────────────────────────────────────

SECONDS_PER_HOUR: int = 3600

# ── Cache TTLs (seconds) ──────────────────────────────────────────────────────

FILE_TREE_TTL: int = 3600       # 1 hour
ISSUES_SYNC_TTL: int = 3600     # 1 hour — issue list cache considered stale

# ── Model routing defaults ────────────────────────────────────────────────────

MODEL_HAIKU: str = "claude-haiku-4-5-20251001"
MODEL_SONNET: str = "claude-sonnet-4-6"
MODEL_OPUS: str = "claude-opus-4-6"

VALID_MODELS: tuple[str, ...] = (MODEL_HAIKU, MODEL_SONNET, MODEL_OPUS)

# ── Analysis / batching ───────────────────────────────────────────────────────

ANALYSIS_BATCH_SIZE: int = 5
ANALYSIS_BATCH_SIZE_MAX: int = 20
ANALYSIS_BATCH_SIZE_MIN: int = 1

# ── Test quality gates ────────────────────────────────────────────────────────

COVERAGE_THRESHOLD: int = 80  # minimum coverage % to pass verify step (only change via /th:settings)
