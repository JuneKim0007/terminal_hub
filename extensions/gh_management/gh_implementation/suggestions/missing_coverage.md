# Missing Coverage Fix Guide

- Run `python -m pytest --cov=terminal_hub --cov=extensions --cov-report=term-missing` to see uncovered lines
- Focus on uncovered branches: `if/else` blocks, `try/except` handlers, early returns
- Add one test per uncovered branch — test the condition that triggers each path
- Parameterize tests where multiple similar inputs should all be covered
- Check for dead code: if a branch is impossible to reach, remove it rather than testing it
