"""Tests for sanitize_params recursion depth limit (#135)."""

from safeclaw.utils.sanitize import (
    _MAX_SANITIZE_DEPTH,
    sanitize_list,
    sanitize_params,
    sanitize_string,
)


def test_sanitize_string_strips_control_chars():
    """Baseline: control characters are removed."""
    assert sanitize_string("hello\x00world") == "helloworld"
    assert sanitize_string("tab\there") == "tab\there"  # \t (0x09) is kept


def test_sanitize_recurses_nested_dicts():
    """Nested dicts are sanitized at each level."""
    nested = {"a": {"b": {"c": "val\x00ue"}}}
    result = sanitize_params(nested)
    assert result == {"a": {"b": {"c": "value"}}}


def test_sanitize_recurses_nested_lists():
    """Nested lists are sanitized at each level."""
    nested = {"items": [["hello\x00", ["\x01inner"]]]}
    result = sanitize_params(nested)
    assert result == {"items": [["hello", ["inner"]]]}


def test_sanitize_handles_deeply_nested_without_crash():
    """A payload nested 200 levels deep must not raise RecursionError.

    Instead, once _MAX_SANITIZE_DEPTH is reached the content is truncated
    to an empty dict/list.
    """
    # Build a 200-level nested dict: {"k": {"k": {"k": ... "leaf" ...}}}
    depth = 200
    payload: dict = {"leaf": "deep\x00value"}
    for _ in range(depth):
        payload = {"k": payload}

    # Must not raise RecursionError
    result = sanitize_params(payload)

    # Walk down to the depth limit — at _MAX_SANITIZE_DEPTH we get {}
    node = result
    for i in range(_MAX_SANITIZE_DEPTH):
        assert isinstance(node, dict), f"Expected dict at depth {i}, got {type(node)}"
        if "k" in node:
            node = node["k"]
        else:
            # Reached an empty dict from truncation
            assert node == {}, f"Expected empty dict at depth {i}, got {node}"
            break
    else:
        # After _MAX_SANITIZE_DEPTH steps of "k", the next level should be {}
        assert node == {}, f"Expected empty dict at max depth, got {node}"


def test_sanitize_deeply_nested_lists_without_crash():
    """A list nested 200 levels deep must not crash."""
    depth = 200
    payload: list = ["deep\x00value"]
    for _ in range(depth):
        payload = [payload]

    result = sanitize_list(payload)

    # Walk down to the depth limit
    node = result
    for i in range(_MAX_SANITIZE_DEPTH):
        assert isinstance(node, list), f"Expected list at depth {i}, got {type(node)}"
        if len(node) > 0 and isinstance(node[0], list):
            node = node[0]
        else:
            # Either empty from truncation or a leaf value
            break
    # At or beyond max depth the list should be empty
    if isinstance(node, list) and len(node) > 0 and isinstance(node[0], list):
        # Still nested — that means we hit an empty list from truncation
        assert node[0] == []


def test_sanitize_mixed_nesting():
    """Mixed dict/list nesting is handled correctly."""
    payload = {"a": [{"b": [{"c": "dirty\x07string"}]}]}
    result = sanitize_params(payload)
    assert result == {"a": [{"b": [{"c": "dirtystring"}]}]}


def test_max_sanitize_depth_is_32():
    """Ensure the constant has the expected value."""
    assert _MAX_SANITIZE_DEPTH == 32


def test_sanitize_params_preserves_non_string_values():
    """Ints, floats, bools, None should pass through unchanged."""
    payload = {"count": 42, "rate": 3.14, "active": True, "extra": None}
    result = sanitize_params(payload)
    assert result == payload


def test_sanitize_params_empty_dict():
    """Empty dict returns empty dict."""
    assert sanitize_params({}) == {}


def test_sanitize_list_empty():
    """Empty list returns empty list."""
    assert sanitize_list([]) == []
