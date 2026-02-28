"""Ontology consistency validation — advisory checks at startup."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from safeclaw.engine.knowledge_graph import KnowledgeGraph, SC, SP

if TYPE_CHECKING:
    from safeclaw.engine.class_hierarchy import ClassHierarchy

logger = logging.getLogger("safeclaw.validator")


class OntologyValidator:
    """Validates ontology consistency and reports warnings.

    Advisory only — does not block startup.
    """

    def __init__(self, kg: KnowledgeGraph, hierarchy: ClassHierarchy):
        self.kg = kg
        self.hierarchy = hierarchy

    def validate(self) -> list[str]:
        """Run all validation checks. Returns list of warning messages."""
        warnings: list[str] = []
        warnings.extend(self._check_dangling_references())
        warnings.extend(self._check_role_contradictions())
        warnings.extend(self._check_missing_defaults())
        warnings.extend(self._check_orphan_classes())
        return warnings

    def _check_dangling_references(self) -> list[str]:
        """Policies sp:appliesTo a class that doesn't exist in ontology."""
        warnings = []
        results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?policy ?target WHERE {{
                ?policy sp:appliesTo ?target .
            }}
        """)
        known_classes = set(self.hierarchy.get_subclasses("Action"))
        for r in results:
            target_uri = str(r["target"])
            cls = target_uri.rsplit("#", 1)[-1] if "#" in target_uri else target_uri
            if cls not in known_classes:
                warnings.append(
                    f"Dangling reference: policy {r['policy']} applies to "
                    f"unknown class '{cls}'"
                )
        return warnings

    def _check_role_contradictions(self) -> list[str]:
        """Roles that allow AND deny the same class (or parent/child conflict)."""
        warnings = []
        results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?role ?allowed ?denied WHERE {{
                ?role sp:allowsAction ?allowed .
                ?role sp:deniesAction ?denied .
            }}
        """)
        for r in results:
            allowed_uri = str(r["allowed"])
            denied_uri = str(r["denied"])
            allowed_cls = (
                allowed_uri.rsplit("#", 1)[-1] if "#" in allowed_uri else allowed_uri
            )
            denied_cls = (
                denied_uri.rsplit("#", 1)[-1] if "#" in denied_uri else denied_uri
            )
            # Direct conflict
            if allowed_cls == denied_cls:
                warnings.append(
                    f"Role contradiction: {r['role']} both allows and denies '{allowed_cls}'"
                )
            # Hierarchy conflict: allowed is subclass of denied
            elif self.hierarchy.is_subclass_of(allowed_cls, denied_cls):
                warnings.append(
                    f"Role contradiction: {r['role']} allows '{allowed_cls}' "
                    f"but denies parent '{denied_cls}'"
                )
        return warnings

    def _check_missing_defaults(self) -> list[str]:
        """Action classes without sc:hasRiskLevel defined."""
        warnings = []
        all_action_classes = self.hierarchy.get_subclasses("Action")
        for cls in sorted(all_action_classes):
            if cls == "Action":
                continue
            if self.hierarchy.get_defaults(cls) is None:
                warnings.append(f"Missing defaults: '{cls}' has no risk level defined")
        return warnings

    def _check_orphan_classes(self) -> list[str]:
        """Classes declared as owl:Class in sc: namespace but not in the Action hierarchy."""
        warnings = []
        results = self.kg.query(f"""
            PREFIX sc: <{SC}>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT ?cls WHERE {{
                ?cls a owl:Class .
                FILTER(STRSTARTS(STR(?cls), "{SC}"))
            }}
        """)
        action_hierarchy = self.hierarchy.get_subclasses("Action")
        # Also exclude non-action classes that are expected (RiskLevel, AffectsScope, etc.)
        non_action_classes = {"RiskLevel", "AffectsScope"}
        for r in results:
            cls = str(r["cls"]).rsplit("#", 1)[-1]
            if cls not in action_hierarchy and cls not in non_action_classes:
                warnings.append(
                    f"Orphan class: '{cls}' is not part of the Action hierarchy"
                )
        return warnings
