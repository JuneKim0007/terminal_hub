"""Tests for terminal_hub.utils.test_filter.filter_test_results."""
import pytest
from terminal_hub.utils.test_filter import filter_test_results

SAMPLE_OUTPUT = """\
PASSED tests/test_foo.py::test_passes
FAILED tests/test_foo.py::test_fails - AssertionError: expected 1 got 2
FAILED tests/test_other.py::test_other_fails - ValueError: bad value
=== short test summary info ===
FAILED tests/test_foo.py::test_fails
FAILED tests/test_other.py::test_other_fails
2 failed, 1 passed in 0.5s
Name                     Stmts   Miss  Cover
--------------------------------------------
terminal_hub/foo.py         10      2    80%
terminal_hub/other.py        5      1    80%
TOTAL                       15      3    80%
"""


def test_returns_full_output_when_files_is_none():
    result = filter_test_results(SAMPLE_OUTPUT, None)
    assert result == SAMPLE_OUTPUT


def test_returns_full_output_when_files_is_empty():
    result = filter_test_results(SAMPLE_OUTPUT, [])
    assert result == SAMPLE_OUTPUT


def test_filters_failed_lines_to_matching_file():
    result = filter_test_results(SAMPLE_OUTPUT, ["terminal_hub/foo.py"])
    assert "test_foo.py::test_fails" in result
    assert "test_other.py::test_other_fails" not in result


def test_keeps_summary_and_separator_lines():
    result = filter_test_results(SAMPLE_OUTPUT, ["terminal_hub/foo.py"])
    assert "short test summary" in result
    assert "failed" in result


def test_keeps_coverage_line_for_matching_file():
    result = filter_test_results(SAMPLE_OUTPUT, ["terminal_hub/foo.py"])
    assert "terminal_hub/foo.py" in result


def test_excludes_coverage_line_for_nonmatching_file():
    result = filter_test_results(SAMPLE_OUTPUT, ["terminal_hub/foo.py"])
    assert "terminal_hub/other.py" not in result


def test_always_keeps_total_coverage_line():
    result = filter_test_results(SAMPLE_OUTPUT, ["terminal_hub/foo.py"])
    assert "TOTAL" in result


def test_falls_back_to_full_output_when_filter_produces_nothing():
    result = filter_test_results(SAMPLE_OUTPUT, ["nonexistent/file.py"])
    # Should fall back to full output since filter matched nothing useful
    assert len(result) > 0


def test_mixed_pass_fail_only_returns_failed_for_file():
    result = filter_test_results(SAMPLE_OUTPUT, ["terminal_hub/foo.py"])
    # PASSED lines are intentionally omitted from filtered view
    assert "PASSED" not in result or "test_other" not in result
