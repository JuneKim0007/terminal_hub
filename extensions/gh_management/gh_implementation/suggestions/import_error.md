# Import Error Fix Guide

- Check `affected_files` for missing `__init__.py` in any new package directory
- Verify the import path matches the actual file location — run `python -c "import <module>"` to confirm
- Look for circular imports: if module A imports B and B imports A, extract shared code to a third module
- Check `pyproject.toml` or `setup.py` for missing package declarations
- If a new dependency was added, ensure it is installed: `pip install -e .`
