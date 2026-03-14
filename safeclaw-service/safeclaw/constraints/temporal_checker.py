"""Temporal checker - validates actions against time-window constraints."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP, SC

logger = logging.getLogger("safeclaw.temporal")

_SAFE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class TemporalCheckResult:
    violated: bool
    reason: str = ""


@dataclass
class _TemporalConstraint:
    """A single cached temporal constraint."""

    action_class: str  # local name (e.g. "DeployAction")
    not_before: datetime | None
    not_after: datetime | None


class TemporalChecker:
    """Checks actions against temporal constraints (sp:notBefore, sp:notAfter).

    When a ``knowledge_graph`` is provided at construction time the SPARQL
    query is executed once and the results are cached.  The ``reload()``
    method can be called to refresh the cache after ontology changes.
    """

    _TEMPORAL_QUERY = f"""
        PREFIX sp: <{SP}>
        PREFIX sc: <{SC}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?actionClass ?notBefore ?notAfter WHERE {{
            ?constraint a sp:TemporalConstraint ;
                        sp:appliesTo ?actionClass .
            OPTIONAL {{ ?constraint sp:notBefore ?notBefore }}
            OPTIONAL {{ ?constraint sp:notAfter ?notAfter }}
        }}
    """

    def __init__(self, knowledge_graph: KnowledgeGraph | None = None):
        self._kg = knowledge_graph
        # Map from action class local name to list of constraints
        self._constraints: dict[str, list[_TemporalConstraint]] = {}
        self._loaded = False
        if knowledge_graph is not None:
            self._load_constraints(knowledge_graph)

    def _load_constraints(self, knowledge_graph: KnowledgeGraph) -> None:
        """Execute SPARQL once and cache temporal constraints."""
        self._constraints.clear()
        self._loaded = True
        results = knowledge_graph.query(self._TEMPORAL_QUERY)
        for row in results:
            action_uri = str(row["actionClass"])
            action_local = action_uri.rsplit("#", 1)[-1] if "#" in action_uri else action_uri
            not_before_raw = row.get("notBefore")
            not_after_raw = row.get("notAfter")
            not_before = self._parse_datetime(not_before_raw, "notBefore", action_local)
            not_after = self._parse_datetime(not_after_raw, "notAfter", action_local)
            constraint = _TemporalConstraint(
                action_class=action_local,
                not_before=not_before,
                not_after=not_after,
            )
            self._constraints.setdefault(action_local, []).append(constraint)

    @staticmethod
    def _parse_datetime(raw: object | None, field_name: str, action_class: str) -> datetime | None:
        """Parse a datetime value from a SPARQL result, returning None on failure."""
        if raw is None:
            return None
        try:
            dt = datetime.fromisoformat(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            logger.warning(
                "Failed to parse %s value %r for %s",
                field_name,
                raw,
                action_class,
            )
            return None

    def reload(self, knowledge_graph: KnowledgeGraph | None = None) -> None:
        """Refresh the constraint cache from the knowledge graph."""
        kg = knowledge_graph or self._kg
        if kg is None:
            logger.warning("reload() called without a knowledge graph — no-op")
            return
        if knowledge_graph is not None:
            self._kg = knowledge_graph
        self._load_constraints(kg)

    def check(
        self, action: ClassifiedAction, knowledge_graph: KnowledgeGraph
    ) -> TemporalCheckResult:
        """Check action against temporal constraints.

        If constraints were cached at init time, uses the cache.
        Otherwise falls back to an on-the-fly SPARQL query (legacy path).
        """
        if not _SAFE_ID.match(action.ontology_class):
            return TemporalCheckResult(violated=False)

        # If constraints were not loaded at init time (legacy usage where the KG
        # is passed only to check()), do a one-time load from the provided KG.
        if not self._loaded:
            self._kg = knowledge_graph
            self._load_constraints(knowledge_graph)

        constraints = self._constraints.get(action.ontology_class, [])

        if not constraints:
            return TemporalCheckResult(violated=False)

        now = datetime.now(timezone.utc)

        for c in constraints:
            if c.not_before is not None:
                if now < c.not_before:
                    return TemporalCheckResult(
                        violated=True,
                        reason=(
                            f"Action '{action.ontology_class}' not allowed before "
                            f"{c.not_before.isoformat()}"
                        ),
                    )

            if c.not_after is not None:
                if now > c.not_after:
                    return TemporalCheckResult(
                        violated=True,
                        reason=(
                            f"Action '{action.ontology_class}' not allowed after "
                            f"{c.not_after.isoformat()}"
                        ),
                    )

        return TemporalCheckResult(violated=False)
