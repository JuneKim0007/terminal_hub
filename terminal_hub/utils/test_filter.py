"""filter_test_results — single exportable function for filtering pytest output.

Import only from here. Never duplicate this logic elsewhere.
If this function is renamed, update the import in the MCP tool that calls it.
"""
from __future__ import annotations

import re
from pathlib import Path

# Matches pytest count summary lines: "2 failed, 1 passed in 0.50s"
_SUMMARY_RE = re.compile(r"^\d+ (passed|failed|error)")


def filter_test_results(output: str, files: list[str] | None) -> str:
    """Filter raw pytest output to lines relevant to the given source files.

    Args:
        output: Raw pytest stdout (combined stdout + stderr).
        files:  List of source file paths to filter by, e.g.
                ['terminal_hub/foo.py', 'extensions/bar/__init__.py'].
                Pass None or [] to return the full output unfiltered.

    Returns:
        Filtered pytest output string. Falls back to full output if the
        filter would produce an empty result (avoids silent data loss).
    """
    if not files:
        return output

    # Build stems: 'terminal_hub/foo.py' → {'foo', 'test_foo'}
    stems: set[str] = set()
    for f in files:
        stem = Path(f).stem
        stems.add(stem)
        stems.add(f"test_{stem}")

    filtered: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()

        # Always keep: separator lines (=== ... === and --- ... ---)
        if stripped.startswith("=") or stripped.startswith("-"):
            filtered.append(line)
            continue

        # Always keep: count summary lines ("2 failed, 1 passed in 0.5s")
        if _SUMMARY_RE.match(stripped):
            filtered.append(line)
            continue

        # Always keep: short test summary section header
        if stripped.startswith("short test summary"):
            filtered.append(line)
            continue

        # FAILED / ERROR lines: keep only if a stem appears in the line
        if stripped.startswith(("FAILED ", "ERROR ")):
            if any(stem in stripped for stem in stems):
                filtered.append(line)
            continue

        # PASSED lines: always skip (not useful in filtered view)
        if stripped.startswith("PASSED "):
            continue

        # Coverage table — TOTAL line: always keep
        if stripped.startswith("TOTAL"):
            filtered.append(line)
            continue

        # Everything else (coverage body lines, tracebacks): keep if stem matches
        if any(stem in stripped for stem in stems):
            filtered.append(line)

    # Fall back to full output if filter produced nothing useful
    return "\n".join(filtered) if filtered else output
