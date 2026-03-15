"""Normalize issue titles into filesystem-safe kebab-case slugs."""
import re


def slugify(title: str) -> str:
    """Convert a title to a kebab-case slug.

    Rules: lowercase, strip non-alphanumeric except spaces and hyphens,
    replace spaces/hyphens with single hyphens, truncate at 60 characters,
    strip leading/trailing hyphens.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug.strip())
    slug = slug[:60]
    slug = slug.strip("-")
    return slug
