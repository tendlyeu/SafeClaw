"""Prompt-injection pattern scoring.

Shared by the inbound-message gate (`/evaluate/inbound-message`) and the
tool-result recording path so that external content re-entering the agent
context — fetched web pages, browser snapshots — is scored with the same
patterns as inbound channel messages (#326).
"""

from __future__ import annotations

import re

# (compiled pattern, flag) — flags are prefixed `prompt_injection_` so callers
# can count injection signals distinctly from other flags.
INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
        ),
        "prompt_injection_ignore_instructions",
    ),
    (
        re.compile(r"(?i)you\s+are\s+now\s+(a|an|in)\s+"),
        "prompt_injection_role_override",
    ),
    (
        re.compile(r"(?i)system\s*prompt\s*[:=]"),
        "prompt_injection_system_prompt",
    ),
    (
        re.compile(
            r"(?i)(do\s+not|don'?t)\s+follow\s+(your|the)\s+(rules|guidelines|instructions)",
        ),
        "prompt_injection_rule_override",
    ),
    (
        re.compile(
            r"(?i)\[/?INST\]|\[/?SYS\]|<\|im_start\|>|<\|im_end\|>",
        ),
        "prompt_injection_special_tokens",
    ),
    (
        re.compile(r"(?i)pretend\s+(you\s+)?(are|to\s+be)\s+"),
        "prompt_injection_pretend",
    ),
]


def score_injection(text: str) -> list[str]:
    """Return the list of prompt-injection flags matched in ``text``."""
    if not text:
        return []
    return [flag for pattern, flag in INJECTION_PATTERNS if pattern.search(text)]
