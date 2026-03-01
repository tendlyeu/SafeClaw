"""Derived constraint rules - Python-based reasoning over the knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.constraints.preference_checker import UserPreferences
from safeclaw.engine.knowledge_graph import KnowledgeGraph

if TYPE_CHECKING:
    from safeclaw.engine.class_hierarchy import ClassHierarchy


@dataclass
class DerivedCheckResult:
    requires_confirmation: bool
    derived_rules: list[str] = field(default_factory=list)
    reason: str = ""


class DerivedConstraintChecker:
    """Derives new constraints from the ontology using Python logic.

    Implements rules that would typically be expressed as N3/EYE rules
    but are implemented here in Python with RDFLib/pySHACL.
    """

    def __init__(
        self, knowledge_graph: KnowledgeGraph, hierarchy: ClassHierarchy | None = None
    ):
        self.kg = knowledge_graph
        self._hierarchy = hierarchy

    def check(
        self,
        action: ClassifiedAction,
        user_prefs: UserPreferences,
        session_history: list[str],
    ) -> DerivedCheckResult:
        """Run all derived constraint rules against the action."""
        triggered_rules: list[str] = []
        reasons: list[str] = []

        # Rule 1: Critical + Irreversible → requires confirmation
        if self._check_critical_irreversible(action):
            triggered_rules.append("CriticalIrreversibleRule")
            reasons.append(
                f"Action '{action.ontology_class}' is CriticalRisk and irreversible"
            )

        # Rule 2: SharedState + cautious/supervised user → requires confirmation
        if self._check_shared_state_cautious(action, user_prefs):
            triggered_rules.append("SharedStateCautiousRule")
            reasons.append(
                f"Action affects SharedState and user autonomy is '{user_prefs.autonomy_level}'"
            )

        # Rule 3: Cumulative risk escalation
        if self._check_cumulative_risk(session_history):
            triggered_rules.append("CumulativeRiskRule")
            reasons.append(
                "Session risk threshold exceeded (3+ MediumRisk or 2+ HighRisk actions)"
            )

        if triggered_rules:
            return DerivedCheckResult(
                requires_confirmation=True,
                derived_rules=triggered_rules,
                reason="; ".join(reasons),
            )

        return DerivedCheckResult(requires_confirmation=False)

    def _check_critical_irreversible(self, action: ClassifiedAction) -> bool:
        """Rule 1: CriticalRisk AND not reversible → requires confirmation."""
        return action.risk_level == "CriticalRisk" and not action.is_reversible

    def _check_shared_state_cautious(
        self, action: ClassifiedAction, user_prefs: UserPreferences
    ) -> bool:
        """Rule 2: SharedState scope + cautious/supervised autonomy → requires confirmation."""
        return (
            action.affects_scope == "SharedState"
            and user_prefs.autonomy_level in ("cautious", "supervised")
        )

    def _check_cumulative_risk(self, session_history: list[str]) -> bool:
        """Rule 4: 3+ MediumRisk or 2+ HighRisk actions in session → escalate."""
        medium_count = 0
        high_count = 0

        for entry in session_history:
            if "MediumRisk" in entry:
                medium_count += 1
            elif "HighRisk" in entry:
                high_count += 1
            elif "CriticalRisk" in entry:
                high_count += 1

        return medium_count >= 3 or high_count >= 2
