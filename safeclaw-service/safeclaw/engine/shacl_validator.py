"""SHACL validator wrapper - real-time constraint validation via pySHACL."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph

logger = logging.getLogger("safeclaw.shacl")


@dataclass
class SHACLResult:
    conforms: bool
    violations: list[dict] = field(default_factory=list)

    @property
    def first_violation_message(self) -> str:
        if self.violations:
            return self.violations[0].get("message", "SHACL constraint violated")
        return ""


class SHACLValidator:
    """Validates RDF data against SHACL shape graphs."""

    def __init__(self):
        self.shapes_graph = Graph()

    def load_shapes(self, shapes_dir: Path) -> None:
        for shape_file in shapes_dir.glob("*.ttl"):
            logger.info(f"Loading SHACL shapes: {shape_file.name}")
            self.shapes_graph.parse(str(shape_file), format="turtle")
        logger.info(f"Loaded {len(self.shapes_graph)} SHACL triples")

    def validate(self, data_graph: Graph) -> SHACLResult:
        """Validate an RDF data graph against loaded SHACL shapes."""
        if len(self.shapes_graph) == 0:
            return SHACLResult(conforms=True)

        try:
            from pyshacl import validate

            conforms, results_graph, results_text = validate(
                data_graph=data_graph,
                shacl_graph=self.shapes_graph,
                inference="none",
            )

            violations = []
            if not conforms:
                violations = self._parse_violations(results_graph)

            return SHACLResult(conforms=conforms, violations=violations)
        except Exception as e:
            logger.error(f"SHACL validation error: {e}")
            return SHACLResult(conforms=False, violations=[{"message": "SHACL validation failed due to an internal error"}])

    def _parse_violations(self, results_graph: Graph) -> list[dict]:
        from rdflib import SH
        violations = []
        for result_node in results_graph.subjects(
            predicate=SH.resultMessage
        ):
            message = str(results_graph.value(result_node, SH.resultMessage) or "")
            shape = str(results_graph.value(result_node, SH.sourceShape) or "")
            violations.append({"message": message, "shape": shape})
        if not violations:
            violations.append({"message": "SHACL constraint violated"})
        return violations
