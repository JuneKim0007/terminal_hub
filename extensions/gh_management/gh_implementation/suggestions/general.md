# General Test Fix Guide

- Read the full error in `filtered_output` carefully — the root cause is usually in the first few lines
- Reproduce the failure: run `python -m pytest <test_path> -v --tb=long` for more context
- Check `affected_files` for recent changes that may have broken assumptions
- Verify all fixtures and test setup are correct — stale fixtures cause subtle failures
- If multiple tests fail, fix them in isolation starting with the most fundamental (lowest-level) one
