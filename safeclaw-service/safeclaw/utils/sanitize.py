"""Input sanitization utilities for SafeClaw.

Extracted from api/routes.py so that both the API layer and the engine layer
can sanitize inputs without circular imports.
"""

import re

# Regex to strip control characters (keep printable + whitespace)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_RESULT_LEN = 100_000

# Maximum recursion depth for nested dict/list sanitization.
# Deeply nested payloads beyond this limit are truncated to prevent
# RecursionError from malicious input.
_MAX_SANITIZE_DEPTH = 32


def sanitize_string(value: str) -> str:
    """Strip control characters and limit length to prevent prompt injection."""
    sanitized = _CONTROL_CHAR_RE.sub("", value)
    return sanitized[:_MAX_RESULT_LEN]


def sanitize_list(items: list, _depth: int = 0) -> list:
    """Recursively sanitize values in a list.

    Args:
        items: The list to sanitize.
        _depth: Current recursion depth (internal use). When _depth exceeds
            _MAX_SANITIZE_DEPTH, returns an empty list to prevent stack overflow.
    """
    if _depth >= _MAX_SANITIZE_DEPTH:
        return []
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(sanitize_string(item))
        elif isinstance(item, dict):
            result.append(sanitize_params(item, _depth=_depth + 1))
        elif isinstance(item, list):
            result.append(sanitize_list(item, _depth=_depth + 1))
        else:
            result.append(item)
    return result


def sanitize_params(params: dict, _depth: int = 0) -> dict:
    """Recursively sanitize string values in params dict (handles arbitrary nesting).

    Args:
        params: The dictionary to sanitize.
        _depth: Current recursion depth (internal use). When _depth exceeds
            _MAX_SANITIZE_DEPTH, returns an empty dict to prevent stack overflow.
    """
    if _depth >= _MAX_SANITIZE_DEPTH:
        return {}
    sanitized = {}
    for k, v in params.items():
        key = sanitize_string(str(k))
        if isinstance(v, str):
            sanitized[key] = sanitize_string(v)
        elif isinstance(v, dict):
            sanitized[key] = sanitize_params(v, _depth=_depth + 1)
        elif isinstance(v, list):
            sanitized[key] = sanitize_list(v, _depth=_depth + 1)
        else:
            sanitized[key] = v
    return sanitized
