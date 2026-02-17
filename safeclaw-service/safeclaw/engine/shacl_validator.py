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
                violations = self._parse_violations(results_text)

            return SHACLResult(conforms=conforms, violations=violations)
        except Exception as e:
            logger.error(f"SHACL validation error: {e}")
            return SHACLResult(conforms=True)

    def _parse_violations(self, results_text: str) -> list[dict]:
        violations = []
        current = {}
        for line in results_text.split("\n"):
            line = line.strip()
            if line.startswith("Message:"):
                current["message"] = line.replace("Message:", "").strip()
            elif line.startswith("Source Shape:"):
                current["shape"] = line.replace("Source Shape:", "").strip()
            elif line == "" and current:
                violations.append(current)
                current = {}
        if current:
            violations.append(current)
        return violations
