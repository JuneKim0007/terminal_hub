"""Tests for run_tests_filtered — parses a pytest run into a verdict.

It shells out to pytest and reads the result back out of stdout with regexes,
so the parsing is the behaviour worth pinning. Notably, this is the tool that
reports coverage and it was itself the least-covered function in its module.
"""
from unittest.mock import MagicMock, patch

import pytest

from extensions.gh_management.gh_implementation import _do_run_tests_filtered
from terminal_hub.config import COVERAGE_THRESHOLD

_GREEN = """\
tests/test_a.py ..
TOTAL                     4912    263    95%
Required test coverage of 80% reached. Total coverage: 95.00%
1200 passed in 2.10s
"""

_RED = """\
FAILED tests/test_a.py::test_one - AssertionError
FAILED tests/test_b.py::test_two - ValueError
TOTAL                     4912   1200    60%
2 failed, 1198 passed in 2.30s
"""


def run(stdout, returncode):
    proc = MagicMock(stdout=stdout, stderr="", returncode=returncode)
    with patch("subprocess.run", return_value=proc):
        return _do_run_tests_filtered(None)


def test_a_green_run_reports_pass_and_reads_the_coverage_total():
    result = run(_GREEN, returncode=0)

    assert result["passed"] is True
    assert result["failed"] == 0
    assert result["coverage"] == 95.0
    assert result["meets_threshold"] is True
    assert result["threshold"] == COVERAGE_THRESHOLD
    assert "1200 passed" in result["_display"]


def test_failures_are_counted_and_reported_as_not_passing():
    result = run(_RED, returncode=1)

    assert result["passed"] is False
    assert result["failed"] == 2
    assert "2 failed" in result["_display"]


def test_coverage_below_the_threshold_is_flagged():
    result = run(_RED, returncode=1)

    assert result["coverage"] == 60.0
    assert result["meets_threshold"] is False


def test_unparseable_output_degrades_to_zero_rather_than_raising():
    """A crashed pytest prints no summary; the tool must still return a verdict."""
    result = run("collection error: no tests ran\n", returncode=2)

    assert result["coverage"] == 0.0
    assert result["passed"] is False
    assert result["meets_threshold"] is False
