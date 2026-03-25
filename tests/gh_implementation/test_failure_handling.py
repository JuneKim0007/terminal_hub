"""Tests for gh_implementation failure classification."""
from extensions.gh_management.gh_implementation import _classify_test_failure


def test_classifies_import_error():
    output = "FAILED tests/test_foo.py::test_bar\nImportError: No module named 'foo'"
    assert _classify_test_failure(output, 1, 85.0, 80.0) == "import_error"


def test_classifies_module_not_found():
    output = "ModuleNotFoundError: No module named 'bar'"
    assert _classify_test_failure(output, 1, 90.0, 80.0) == "import_error"


def test_classifies_assertion_error():
    output = "FAILED tests/test_foo.py::test_bar\nAssertionError: expected 1 got 2"
    assert _classify_test_failure(output, 1, 90.0, 80.0) == "assertion_error"


def test_classifies_missing_coverage_when_no_failures():
    output = "1 passed in 0.5s\nTOTAL  100  20  80%"
    assert _classify_test_failure(output, 0, 79.0, 80.0) == "missing_coverage"


def test_classifies_import_error_over_assertion_error():
    # import_error check runs first
    output = "ImportError: ...\nAssertionError: ..."
    assert _classify_test_failure(output, 2, 50.0, 80.0) == "import_error"


def test_classifies_general_for_unknown():
    output = "FAILED tests/test_foo.py::test_bar\nRuntimeError: something unexpected"
    assert _classify_test_failure(output, 1, 90.0, 80.0) == "general"


def test_missing_coverage_requires_zero_failed():
    # if there are failures AND low coverage, classify by failure type not coverage
    output = "AssertionError: expected 1 got 2"
    assert _classify_test_failure(output, 1, 70.0, 80.0) == "assertion_error"
