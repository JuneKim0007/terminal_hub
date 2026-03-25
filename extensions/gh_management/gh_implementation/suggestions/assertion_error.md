# Assertion Error Fix Guide

- Read the full traceback in `filtered_output` — the assertion message shows expected vs actual
- Check if the test uses hardcoded expected values that need updating after the implementation change
- Verify mock objects return the correct type and shape — prefer real objects where possible
- Look for off-by-one errors in list indexing, range boundaries, or count expectations
- Run the specific failing test in isolation: `python -m pytest tests/path/test_file.py::test_name -v`
