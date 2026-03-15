import pytest
from terminal_hub.slugify import slugify


@pytest.mark.parametrize("title,expected", [
    ("Fix auth bug", "fix-auth-bug"),
    ("Fix auth bug!", "fix-auth-bug"),
    ("Fix  multiple   spaces", "fix-multiple-spaces"),
    ("UPPERCASE TITLE", "uppercase-title"),
    ("special @#$% chars", "special-chars"),
    ("numbers 123 ok", "numbers-123-ok"),
    ("trailing-hyphens-", "trailing-hyphens"),
    ("a" * 70, "a" * 60),
    ("Héllo wörld", "hllo-wrld"),
    ("--leading-hyphens", "leading-hyphens"),
])
def test_slugify(title, expected):
    assert slugify(title) == expected
