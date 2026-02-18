"""Message gate - governs outgoing messages with content policies."""

import re
import time
from collections import OrderedDict
from dataclasses import dataclass

from safeclaw.engine.knowledge_graph import KnowledgeGraph, SU

MAX_SESSIONS = 1000

# Patterns that match common secrets/credentials
SENSITIVE_PATTERNS = [
    (r"(?:^|[\s=])(?:[A-Za-z0-9+/]{4}){10,}={1,2}(?:\s|$)", "Base64 encoded string (possible secret)"),
    (r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*\S+",
     "API key or token"),
    (r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+", "Password"),
    (r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b", "GitHub token"),
    (r"\bsk-[A-Za-z0-9]{20,}\b", "OpenAI/Stripe secret key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS Access Key ID"),
    (r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----", "Private key"),
]

# Max messages per session per hour (default)
DEFAULT_MESSAGE_RATE_LIMIT = 50


@dataclass
class MessageCheckResult:
    block: bool
    reason: str = ""
    check_type: str = ""  # "never_contact" | "sensitive_data" | "rate_limit" | "content_policy"


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

    def check(
        self,
        to: str,
        content: str,
        session_id: str,
    ) -> MessageCheckResult:
        """Run all message checks."""
        # 1. Never-contact list
        if to.lower() in self._never_contact:
            return MessageCheckResult(
                block=True,
                reason=f"Recipient '{to}' is on the never-contact list",
                check_type="never_contact",
            )

        # 2. Sensitive data detection
        sensitive = self._check_sensitive_data(content)
        if sensitive:
            return MessageCheckResult(
                block=True,
                reason=f"Message contains sensitive data: {sensitive}",
                check_type="sensitive_data",
            )

        # 3. Rate limiting
        now = time.monotonic()
        cutoff = now - 3600
        counts = self._session_message_counts.get(session_id, [])
        counts = [t for t in counts if t >= cutoff]
        self._session_message_counts[session_id] = counts

        if len(counts) >= self._message_rate_limit:
            return MessageCheckResult(
                block=True,
                reason=f"Message rate limit exceeded: {len(counts)}/{self._message_rate_limit} messages in the last hour",
                check_type="rate_limit",
            )

        return MessageCheckResult(block=False)

    def record_message(self, session_id: str) -> None:
        """Record a sent message for rate limiting."""
        if session_id not in self._session_message_counts:
            self._session_message_counts[session_id] = []
            while len(self._session_message_counts) > MAX_SESSIONS:
                self._session_message_counts.popitem(last=False)
        self._session_message_counts[session_id].append(time.monotonic())

    def _check_sensitive_data(self, content: str) -> str:
        """Check if message content contains sensitive data patterns."""
        for pattern, description in SENSITIVE_PATTERNS:
            if re.search(pattern, content):
                return description
        return ""
