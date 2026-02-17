"""Temporal checker - validates actions against time-window constraints."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP, SC

_SAFE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class TemporalCheckResult:
    violated: bool
    reason: str = ""


class TemporalChecker:
    """Checks actions against temporal constraints (sp:notBefore, sp:notAfter)."""

    def check(
        self, action: ClassifiedAction, knowledge_graph: KnowledgeGraph
    ) -> TemporalCheckResult:
        """Query temporal constraints and compare against current time."""
        if not _SAFE_ID.match(action.ontology_class):
            return TemporalCheckResult(violated=False)
        results = knowledge_graph.query(f"""
            PREFIX sp: <{SP}>
            PREFIX sc: <{SC}>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?notBefore ?notAfter WHERE {{
                ?constraint a sp:TemporalConstraint ;
                            sp:appliesTo ?actionClass .
                sc:{action.ontology_class} rdfs:subClassOf* ?actionClass .
                OPTIONAL {{ ?constraint sp:notBefore ?notBefore }}
                OPTIONAL {{ ?constraint sp:notAfter ?notAfter }}
            }}
        """)

        if not results:
            return TemporalCheckResult(violated=False)

        now = datetime.now(timezone.utc)

        for row in results:
            not_before = row.get("notBefore")
            not_after = row.get("notAfter")

            if not_before is not None:
                try:
                    bound = datetime.fromisoformat(str(not_before))
                    if bound.tzinfo is None:
                        bound = bound.replace(tzinfo=timezone.utc)
                    if now < bound:
                        return TemporalCheckResult(
                            violated=True,
                            reason=(
                                f"Action '{action.ontology_class}' not allowed before "
                                f"{bound.isoformat()}"
                            ),
                        )
                except (ValueError, TypeError):
                    pass

            if not_after is not None:
                try:
                    bound = datetime.fromisoformat(str(not_after))
                    if bound.tzinfo is None:
                        bound = bound.replace(tzinfo=timezone.utc)
                    if now > bound:
                        return TemporalCheckResult(
                            violated=True,
                            reason=(
                                f"Action '{action.ontology_class}' not allowed after "
                                f"{bound.isoformat()}"
                            ),
                        )
                except (ValueError, TypeError):
                    pass

        return TemporalCheckResult(violated=False)
