"""Decision Explainer — turns machine-readable DecisionRecords into plain English."""

import logging

from safeclaw.audit.models import DecisionRecord
from safeclaw.llm.prompts import DECISION_EXPLAINER_SYSTEM, build_explainer_user_prompt

logger = logging.getLogger("safeclaw.llm.explainer")


class DecisionExplainer:
    """Generates human-readable explanations of governance decisions."""

    def __init__(self, client):
        self.client = client

    async def explain(self, record: DecisionRecord) -> str:
        """Generate a 2-3 sentence explanation of a single decision."""
        user_prompt = build_explainer_user_prompt(
            tool_name=record.action.tool_name,
            params=record.action.params,
            ontology_class=record.action.ontology_class,
            risk_level=record.action.risk_level,
            decision=record.decision,
            reason=self._extract_reason(record),
            constraints_checked=[
                {"type": c.constraint_type, "result": c.result, "reason": c.reason}
                for c in record.justification.constraints_checked
            ],
        )

        result = await self.client.chat(
            messages=[
                {"role": "system", "content": DECISION_EXPLAINER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )

        if result is None:
            return self._fallback_explanation(record)

        return result

    async def explain_session(self, records: list[DecisionRecord]) -> str:
        """Summarize all decisions in a session."""
        if not records:
            return "No decisions to explain."

        summary_parts = []
        for r in records:
            reason = self._extract_reason(r)
            summary_parts.append(
                f"- {r.action.tool_name} ({r.action.ontology_class}): {r.decision} — {reason}"
            )

        user_prompt = "Summarize these governance decisions from one session:\n\n" + "\n".join(
            summary_parts
        )

        result = await self.client.chat(
            messages=[
                {"role": "system", "content": DECISION_EXPLAINER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )

        if result is None:
            return self._fallback_session_summary(records)

        return result

    def _extract_reason(self, record: DecisionRecord) -> str:
        """Get the first violated constraint reason, or a default."""
        for check in record.justification.constraints_checked:
            if check.result == "violated":
                return check.reason
        for pref in record.justification.preferences_applied:
            return pref.effect
        return record.decision

    def _fallback_explanation(self, record: DecisionRecord) -> str:
        """Fallback when LLM is unavailable."""
        reason = self._extract_reason(record)
        return (
            f"Tool '{record.action.tool_name}' was {record.decision}. "
            f"Classification: {record.action.ontology_class} ({record.action.risk_level}). "
            f"Reason: {reason}"
        )

    def _fallback_session_summary(self, records: list[DecisionRecord]) -> str:
        allowed = sum(1 for r in records if r.decision == "allowed")
        blocked = sum(1 for r in records if r.decision == "blocked")
        return (
            f"Session summary: {allowed} allowed, {blocked} blocked "
            f"out of {len(records)} total decisions."
        )
