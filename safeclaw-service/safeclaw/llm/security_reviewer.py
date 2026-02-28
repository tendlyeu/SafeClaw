"""Semantic Security Reviewer — catches what rigid symbolic rules miss."""

import logging
from dataclasses import dataclass

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.llm.prompts import SECURITY_REVIEW_SYSTEM, build_security_review_user_prompt

logger = logging.getLogger("safeclaw.llm.security")


@dataclass
class ReviewEvent:
    tool_name: str
    params: dict
    classified_action: ClassifiedAction
    symbolic_decision: str
    session_history: list[str]
    constraints_checked: list[dict]


@dataclass
class SecurityFinding:
    severity: str
    category: str
    description: str
    recommended_action: str
    confidence: float


VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_CATEGORIES = {"obfuscation", "evasion", "multi_step", "novel_risk", "none"}
VALID_ACTIONS = {"log", "escalate_confirmation", "kill_switch"}


class SecurityReviewer:
    """Async security reviewer that runs in parallel with the symbolic engine."""

    def __init__(self, client, engine_ref=None):
        self.client = client
        self.engine = engine_ref

    async def review(self, event: ReviewEvent) -> SecurityFinding | None:
        """Review a tool call for evasion/obfuscation. Returns finding or None."""
        user_prompt = build_security_review_user_prompt(
            tool_name=event.tool_name,
            params=event.params,
            ontology_class=event.classified_action.ontology_class,
            risk_level=event.classified_action.risk_level,
            symbolic_decision=event.symbolic_decision,
            session_history=event.session_history,
            constraints_checked=event.constraints_checked,
        )
        result = await self.client.chat_json(
            messages=[
                {"role": "system", "content": SECURITY_REVIEW_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )
        if result is None:
            return None
        return self._parse_finding(result)

    def _parse_finding(self, data: dict) -> SecurityFinding | None:
        try:
            if not data.get("suspicious", False):
                return None
            severity = data.get("severity", "low")
            category = data.get("category", "novel_risk")
            description = data.get("description", "No description")
            action = data.get("recommended_action", "log")
            confidence = float(data.get("confidence", 0.5))
            if severity not in VALID_SEVERITIES:
                severity = "low"
            if category not in VALID_CATEGORIES:
                category = "novel_risk"
            if action not in VALID_ACTIONS:
                action = "log"
            confidence = max(0.0, min(1.0, confidence))
            return SecurityFinding(
                severity=severity,
                category=category,
                description=description,
                recommended_action=action,
                confidence=confidence,
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("Failed to parse security review response", exc_info=True)
            return None
