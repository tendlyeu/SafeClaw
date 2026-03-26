"""Semantic Security Reviewer — catches what rigid symbolic rules miss."""

import logging
from dataclasses import dataclass

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.engine.event_bus import SafeClawEvent
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
    agent_id: str | None = None


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
        finding = self._parse_finding(result)
        if finding is not None:
            self._execute_recommendation(finding, event)
        return finding

    # Minimum confidence threshold for acting on kill_switch recommendations.
    # Auto-killing an agent based solely on LLM output is dangerous because
    # LLM responses can be wrong, hallucinated, or manipulated via prompt
    # injection. We require high confidence and still only escalate (log a
    # critical warning) rather than executing the kill directly. A human
    # operator should review and call the /agents/{id}/kill endpoint.
    KILL_SWITCH_CONFIDENCE_THRESHOLD = 0.9

    def _execute_recommendation(self, finding: SecurityFinding, event: ReviewEvent) -> None:
        """Act on the recommended action from a security finding.

        For kill_switch recommendations: instead of auto-executing the kill
        (which would let an LLM unilaterally terminate agents), we log a
        CRITICAL event for human review. The kill must be performed by an
        admin via the /agents/{id}/kill API endpoint.
        """
        if finding.recommended_action == "kill_switch":
            agent_id = event.agent_id
            if finding.confidence < self.KILL_SWITCH_CONFIDENCE_THRESHOLD:
                logger.warning(
                    "Kill switch recommended for agent %s but confidence %.2f is below "
                    "threshold %.2f — logging only. Finding: %s",
                    agent_id,
                    finding.confidence,
                    self.KILL_SWITCH_CONFIDENCE_THRESHOLD,
                    finding.description,
                )
                return
            # Escalate for human review instead of auto-killing.
            # Log at CRITICAL level so alerting systems pick it up.
            logger.critical(
                "KILL SWITCH ESCALATION: LLM recommends killing agent %s "
                "(confidence=%.2f, severity=%s, category=%s). "
                "Reason: %s. "
                "ACTION REQUIRED: An admin must review and call "
                "POST /api/v1/agents/%s/kill to execute.",
                agent_id,
                finding.confidence,
                finding.severity,
                finding.category,
                finding.description,
                agent_id,
            )
            # Publish to event bus if available so dashboards can surface it
            if self.engine and hasattr(self.engine, "event_bus"):
                try:
                    self.engine.event_bus.publish(
                        SafeClawEvent(
                            event_type="kill_switch_escalation",
                            severity="critical",
                            title=f"Kill switch escalation for agent {agent_id}",
                            detail=finding.description,
                            metadata={
                                "agent_id": agent_id,
                                "confidence": finding.confidence,
                                "finding_severity": finding.severity,
                                "category": finding.category,
                            },
                        )
                    )
                except Exception:
                    logger.debug("Failed to publish kill_switch escalation event", exc_info=True)

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
