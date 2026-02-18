"""Tests for SHACL validation."""

from pathlib import Path
from unittest.mock import patch

import pytest
from rdflib import Graph, Literal, Namespace, RDF, XSD

from safeclaw.constraints.action_classifier import ActionClassifier
from safeclaw.engine.shacl_validator import SHACLValidator

SC = Namespace("http://safeclaw.uku.ai/ontology/agent#")

_shapes_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies" / "shapes"
_has_shapes = _shapes_dir.exists() and any(_shapes_dir.glob("*.ttl"))
requires_shapes = pytest.mark.skipif(not _has_shapes, reason="SHACL shapes not available")


@requires_shapes
def test_shacl_validator_loads_shapes():
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    assert len(validator.shapes_graph) > 0


@requires_shapes
def test_safe_action_conforms():
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    classifier = ActionClassifier()
    action = classifier.classify("read", {"file_path": "/src/main.py"})
    result = validator.validate(action.as_rdf_graph())
    assert result.conforms is True


@requires_shapes
def test_shell_action_conforms():
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    classifier = ActionClassifier()
    action = classifier.classify("exec", {"command": "ls -la"})
    result = validator.validate(action.as_rdf_graph())
    assert result.conforms is True


def test_empty_shapes_always_conforms():
    validator = SHACLValidator()
    classifier = ActionClassifier()
    action = classifier.classify("exec", {"command": "rm -rf /"})
    result = validator.validate(action.as_rdf_graph())
    assert result.conforms is True


@requires_shapes
def test_shacl_catches_invalid_action():
    """Validates that SHACL catches a known-bad action with duplicate risk levels."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)

    # Build an invalid RDF graph: an sc:Action with two risk levels,
    # violating sh:maxCount 1 on sc:hasRiskLevel from action-shapes.ttl
    g = Graph()
    g.bind("sc", SC)
    action_node = SC["action_invalid_test"]
    g.add((action_node, RDF.type, SC["Action"]))
    g.add((action_node, SC.hasRiskLevel, SC["CriticalRisk"]))
    g.add((action_node, SC.hasRiskLevel, SC["HighRisk"]))
    g.add((action_node, SC.isReversible, Literal(False, datatype=XSD.boolean)))
    g.add((action_node, SC.affectsScope, SC["LocalOnly"]))

    result = validator.validate(g)
    assert result.conforms is False
    assert len(result.violations) > 0


def test_shacl_validation_error_returns_non_conforming():
    """When pyshacl raises an exception, validator should return conforms=False."""
    validator = SHACLValidator()
    # Put a single triple so shapes_graph is non-empty, triggering validation
    validator.shapes_graph.parse(
        data="@prefix sh: <http://www.w3.org/ns/shacl#> . [] a sh:NodeShape .",
        format="turtle",
    )

    classifier = ActionClassifier()
    action = classifier.classify("read", {"file_path": "/test"})

    with patch("pyshacl.validate", side_effect=RuntimeError("mock error")):
        result = validator.validate(action.as_rdf_graph())
        assert result.conforms is False
        assert any("mock error" in v["message"] for v in result.violations)
