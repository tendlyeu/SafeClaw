"""Tests for _glob_match in safeclaw.engine.roles."""

from __future__ import annotations

import pytest

from safeclaw.engine.roles import _glob_match


@pytest.mark.parametrize(
    "path,pattern,expected",
    [
        # Basic wildcard matching
        ("/tmp/foo.py", "/tmp/*.py", True),
        ("/tmp/foo.txt", "/tmp/*.py", False),
        # Recursive ** matching across directories
        ("/a/b/c/d.py", "/a/**/d.py", True),
        ("/a/d.py", "/a/**/d.py", True),
        ("/a/b/c", "/a/**", True),
        # Exact match
        ("/tmp/foo", "/tmp/foo", True),
        ("/tmp/foo", "/tmp/bar", False),
        # Leading ** (no prefix before **)
        ("/a/b/c.py", "**/*.py", True),
        # Empty path should not match
        ("", "**", False),
        # Single ** matches everything non-empty
        ("/anything/at/all", "**", True),
        # ** in the middle with nested dirs
        ("/root/a/b/c/file.txt", "/root/**/file.txt", True),
        # ** at end matches nested content
        ("/secrets/deep/nested/file", "/secrets/**", True),
        # Single segment wildcard should NOT cross directories
        ("/a/b/c.py", "/a/*.py", False),
        # Pattern with no wildcards — exact match only
        ("/etc/passwd", "/etc/passwd", True),
        ("/etc/shadow", "/etc/passwd", False),
        # Double ** adjacent to other patterns
        ("foo/bar/baz.js", "**/baz.js", True),
        ("foo/bar/baz.js", "foo/**", True),
        # Pattern "**" alone matches any non-empty path
        ("x", "**", True),
    ],
    ids=[
        "wildcard-ext-match",
        "wildcard-ext-no-match",
        "double-star-deep",
        "double-star-immediate",
        "double-star-trailing",
        "exact-match",
        "exact-no-match",
        "leading-double-star",
        "empty-path-no-match",
        "double-star-any",
        "double-star-middle-nested",
        "double-star-trailing-nested",
        "single-star-no-cross-dir",
        "exact-no-wildcard-match",
        "exact-no-wildcard-no-match",
        "leading-double-star-no-slash",
        "trailing-double-star-no-slash",
        "double-star-alone-single-char",
    ],
)
def test_glob_match(path: str, pattern: str, expected: bool) -> None:
    assert _glob_match(path, pattern) == expected
