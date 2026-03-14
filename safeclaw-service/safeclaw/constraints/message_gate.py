"""Message gate - governs outgoing messages with content policies."""

import re
import time
from collections import OrderedDict
from dataclasses import dataclass

from safeclaw.engine.knowledge_graph import KnowledgeGraph, SU

MAX_SESSIONS = 1000

# Patterns that match common secrets/credentials (pre-compiled for performance)
SENSITIVE_PATTERNS = [
    # Base64: match 40+ base64 chars optionally followed by padding.
    # Valid base64 with padding has a last group of 2-3 chars + 1-2 '=' padding,
    # so we allow the final group to be 2-4 chars.
    (re.compile(
        r"(?:^|[\s=])(?:[A-Za-z0-9+/]{4}){9,}[A-Za-z0-9+/]{2,4}={1,2}(?:\s|$)",
        re.MULTILINE,
    ), "Base64 encoded string (possible secret)"),
    (re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*\S+",
    ), "API key or token"),
    (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"), "Password"),
    # GitHub tokens: classic (ghp_/gho_/ghu_/ghs_/ghr_) and fine-grained (github_pat_)
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), "GitHub fine-grained PAT"),
    # OpenAI keys: classic (sk-...) and project-scoped (sk-proj-...)
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9-]{20,}\b"), "OpenAI/Stripe secret key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS Access Key ID"),
    (re.compile(
        r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----", re.MULTILINE,
    ), "Private key"),
]

# Patterns for risk level classification (case-insensitive)
# "high" patterns indicate actual credentials/secrets in the content
HIGH_RISK_PATTERNS = [
    re.compile(r"(?i)-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]

# "medium" patterns indicate sensitive keywords that suggest credential-adjacent content
MEDIUM_RISK_PATTERNS = [
    re.compile(r"(?i)\b(?:password|passwd|pwd)\b"),
    re.compile(r"(?i)\b(?:api[_-]?key)\b"),
    re.compile(r"(?i)\b(?:secret)\b"),
    re.compile(r"(?i)\b(?:token)\b"),
    re.compile(r"(?i)\b(?:credential)\b"),
]

# Max messages per session per hour (default)
DEFAULT_MESSAGE_RATE_LIMIT = 50


@dataclass
class MessageCheckResult:
    block: bool
    reason: str = ""
    check_type: str = ""  # "never_contact" | "sensitive_data" | "rate_limit" | "content_policy"
    risk_level: str = "LowRisk"  # "LowRisk", "MediumRisk", "HighRisk"


class MessageGate:
    """Gates outgoing messages against content policies, contact lists, and rate limits."""

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self._never_contact: set[str] = set()
        self._message_rate_limit = DEFAULT_MESSAGE_RATE_LIMIT
        self._session_message_counts: OrderedDict[str, list[float]] = OrderedDict()
        self._load_contact_policies()

    def _load_contact_policies(self) -> None:
        """Load never-contact list from user preferences in KG."""
        results = self.kg.query(f"""
            PREFIX su: <{SU}>
            SELECT ?contact WHERE {{
                ?user su:hasPreference ?pref .
                ?pref su:neverContact ?contact .
            }}
        """)
        for row in results:
            self._never_contact.add(str(row["contact"]).lower())

    def add_never_contact(self, contact: str) -> None:
        """Add a contact to the never-contact list."""
        self._never_contact.add(contact.lower())

    def remove_never_contact(self, contact: str) -> None:
        """Remove a contact from the never-contact list."""
        self._never_contact.discard(contact.lower())

    def _classify_risk_level(self, content: str) -> str:
        """Classify message risk level based on content patterns.

        Returns "HighRisk" if the content contains actual credentials/secrets,
        "MediumRisk" if it contains sensitive keywords (password, api_key, etc.),
        or "LowRisk" otherwise.
        """
        for pattern in HIGH_RISK_PATTERNS:
            if pattern.search(content):
                return "HighRisk"
        for pattern in MEDIUM_RISK_PATTERNS:
            if pattern.search(content):
                return "MediumRisk"
        return "LowRisk"

    def check(
        self,
        to: str,
        content: str,
        session_id: str,
    ) -> MessageCheckResult:
        """Run all message checks."""
        # Classify risk level based on content
        risk_level = self._classify_risk_level(content)

        # 1. Never-contact list
        if to.lower() in self._never_contact:
            return MessageCheckResult(
                block=True,
                reason=f"Recipient '{to}' is on the never-contact list",
                check_type="never_contact",
                risk_level=risk_level,
            )

        # 2. Sensitive data detection
        sensitive = self._check_sensitive_data(content)
        if sensitive:
            return MessageCheckResult(
                block=True,
                reason=f"Message contains sensitive data: {sensitive}",
                check_type="sensitive_data",
                risk_level=risk_level,
            )

        # 3. Rate limiting (read-only: don't modify _session_message_counts)
        now = time.monotonic()
        cutoff = now - 3600
        counts = self._session_message_counts.get(session_id, [])
        active_count = sum(1 for t in counts if t >= cutoff)

        if active_count >= self._message_rate_limit:
            return MessageCheckResult(
                block=True,
                reason=f"Message rate limit exceeded: {active_count}/{self._message_rate_limit} messages in the last hour",
                check_type="rate_limit",
                risk_level=risk_level,
            )

        return MessageCheckResult(block=False, risk_level=risk_level)

    def record_message(self, session_id: str) -> None:
        """Record a sent message for rate limiting."""
        now = time.monotonic()
        cutoff = now - 3600
        if session_id not in self._session_message_counts:
            self._session_message_counts[session_id] = []
            while len(self._session_message_counts) > MAX_SESSIONS:
                self._session_message_counts.popitem(last=False)
        # Prune expired entries
        self._session_message_counts[session_id] = [
            t for t in self._session_message_counts[session_id] if t >= cutoff
        ]
        self._session_message_counts[session_id].append(now)

    def clear_session(self, session_id: str) -> None:
        """Remove session message counts when session ends."""
        self._session_message_counts.pop(session_id, None)

    def _check_sensitive_data(self, content: str) -> str:
        """Check if message content contains sensitive data patterns."""
        for pattern, description in SENSITIVE_PATTERNS:
            if pattern.search(content):
                return description
        return ""
