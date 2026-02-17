"""Tests for SHACL validation."""

from pathlib import Path

from safeclaw.constraints.action_classifier import ActionClassifier
from safeclaw.engine.shacl_validator import SHACLValidator


def get_shapes_dir() -> Path:
    return Path(__file__).parent.parent / "safeclaw" / "ontologies" / "shapes"


def test_shacl_validator_loads_shapes():
    validator = SHACLValidator()
    shapes_dir = get_shapes_dir()
    if shapes_dir.exists():
        validator.load_shapes(shapes_dir)
        assert len(validator.shapes_graph) > 0


def test_safe_action_conforms():
    validator = SHACLValidator()
    shapes_dir = get_shapes_dir()
    if shapes_dir.exists():
        validator.load_shapes(shapes_dir)

    classifier = ActionClassifier()
    action = classifier.classify("read", {"file_path": "/src/main.py"})
    result = validator.validate(action.as_rdf_graph())
    assert result.conforms is True


def test_shell_action_conforms():
    validator = SHACLValidator()
    shapes_dir = get_shapes_dir()
    if shapes_dir.exists():
        validator.load_shapes(shapes_dir)

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
