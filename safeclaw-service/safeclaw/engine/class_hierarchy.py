"""Class hierarchy service - pure-Python replacement for Java OWL reasoner.

Pre-computes rdfs:subClassOf lookups via SPARQL on the existing KnowledgeGraph.
"""

import logging

from safeclaw.engine.knowledge_graph import KnowledgeGraph, SC

logger = logging.getLogger("safeclaw.hierarchy")

_SC_PREFIX = str(SC)


def _local_name(uri) -> str:
    """Extract local name from a full URI (e.g. 'http://...#ReadFile' -> 'ReadFile')."""
    s = str(uri)
    if "#" in s:
        return s.rsplit("#", 1)[1]
    return s.rsplit("/", 1)[-1]


class ClassHierarchy:
    """Pre-computed class hierarchy from the ontology's rdfs:subClassOf triples.

    Replaces the Java-dependent HermiT reasoner with pure SPARQL traversal.
    """

    def __init__(self, kg: KnowledgeGraph):
        self._superclasses: dict[str, set[str]] = {}
        self._subclasses: dict[str, set[str]] = {}
        self._defaults: dict[str, dict] = {}
        self._build(kg)

    def _build(self, kg: KnowledgeGraph) -> None:
        """Run SPARQL queries to populate caches."""
        # 1. Superclass closure: ?child rdfs:subClassOf* ?parent
        super_results = kg.query(f"""
            PREFIX sc: <{SC}>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?child ?parent WHERE {{
                ?child rdfs:subClassOf* ?parent .
                ?child rdfs:subClassOf* sc:Action .
                ?parent rdfs:subClassOf* sc:Action .
            }}
        """)
        for row in super_results:
            child = _local_name(row["child"])
            parent = _local_name(row["parent"])
            self._superclasses.setdefault(child, set()).add(parent)
            self._subclasses.setdefault(parent, set()).add(child)

        # 2. Ontology-defined defaults (risk, reversibility, scope)
        default_results = kg.query(f"""
            PREFIX sc: <{SC}>
            SELECT ?cls ?risk ?rev ?scope WHERE {{
                ?cls sc:hasRiskLevel ?risk .
                ?cls sc:isReversible ?rev .
                ?cls sc:affectsScope ?scope .
            }}
        """)
        for row in default_results:
            cls = _local_name(row["cls"])
            self._defaults[cls] = {
                "risk_level": _local_name(row["risk"]),
                "is_reversible": str(row["rev"]).lower() in ("true", "1"),
                "affects_scope": _local_name(row["scope"]),
            }

        logger.info(
            "ClassHierarchy built: %d classes, %d with defaults",
            len(self._superclasses),
            len(self._defaults),
        )

    def get_superclasses(self, cls: str) -> set[str]:
        """All ancestors including self.

        For unknown classes not in the hierarchy, returns {cls, "Action"}
        so that prohibitions on the root Action class still apply.
        """
        if cls in self._superclasses:
            return self._superclasses[cls]
        # Unknown class: include "Action" as implicit superclass so that
        # hierarchy-aware prohibitions on Action are not bypassed.
        return {cls, "Action"}

    def get_subclasses(self, cls: str) -> set[str]:
        """All descendants including self."""
        return self._subclasses.get(cls, {cls})

    def get_defaults(self, cls: str) -> dict | None:
        """Ontology-defined risk/reversibility/scope for a class."""
        return self._defaults.get(cls)

    def is_subclass_of(self, cls: str, parent: str) -> bool:
        """Check if cls is equal to or a subclass of parent."""
        return parent in self.get_superclasses(cls)
