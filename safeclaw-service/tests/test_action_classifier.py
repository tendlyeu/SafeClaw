"""Tests for the action classifier."""

from rdflib import Namespace, RDF

from safeclaw.constraints.action_classifier import ActionClassifier

SC = Namespace("http://safeclaw.uku.ai/ontology/agent#")


def test_read_file_classification():
    classifier = ActionClassifier()
    action = classifier.classify("read", {"file_path": "/src/main.py"})
    assert action.ontology_class == "ReadFile"
    assert action.risk_level == "LowRisk"
    assert action.is_reversible is True
    assert action.affects_scope == "LocalOnly"


def test_write_file_classification():
    classifier = ActionClassifier()
    action = classifier.classify("write", {"file_path": "/src/main.py"})
    assert action.ontology_class == "WriteFile"
    assert action.risk_level == "MediumRisk"
    assert action.is_reversible is True


def test_shell_rm_classification():
    classifier = ActionClassifier()
    action = classifier.classify("exec", {"command": "rm -rf /tmp/old"})
    assert action.ontology_class == "DeleteFile"
    assert action.risk_level == "CriticalRisk"
    assert action.is_reversible is False


def test_shell_git_push_classification():
    classifier = ActionClassifier()
    action = classifier.classify("exec", {"command": "git push origin main"})
    assert action.ontology_class == "GitPush"
    assert action.risk_level == "HighRisk"
    assert action.affects_scope == "SharedState"


def test_shell_force_push_classification():
    classifier = ActionClassifier()
    action = classifier.classify("exec", {"command": "git push --force origin main"})
    assert action.ontology_class == "ForcePush"
    assert action.risk_level == "CriticalRisk"
    assert action.is_reversible is False


def test_shell_generic_command():
    classifier = ActionClassifier()
    action = classifier.classify("exec", {"command": "ls -la"})
    assert action.ontology_class == "ExecuteCommand"
    assert action.risk_level == "HighRisk"


def test_message_classification():
    classifier = ActionClassifier()
    action = classifier.classify("message", {"to": "user@email.com", "content": "hello"})
    assert action.ontology_class == "SendMessage"
    assert action.risk_level == "HighRisk"
    assert action.is_reversible is False
    assert action.affects_scope == "ExternalWorld"


def test_web_fetch_classification():
    classifier = ActionClassifier()
    action = classifier.classify("web_fetch", {"url": "https://example.com"})
    assert action.ontology_class == "WebFetch"
    assert action.risk_level == "MediumRisk"


def test_unknown_tool_defaults():
    classifier = ActionClassifier()
    action = classifier.classify("some_unknown_tool", {"param": "value"})
    assert action.ontology_class == "Action"
    assert action.risk_level == "MediumRisk"


def test_chained_command_highest_risk():
    """Chained shell commands should classify by highest-risk sub-command."""
    classifier = ActionClassifier()
    action = classifier.classify("exec", {"command": "ls -la && git push --force origin main"})
    assert action.ontology_class == "ForcePush"
    assert action.risk_level == "CriticalRisk"


def test_action_rdf_graph():
    classifier = ActionClassifier()
    action = classifier.classify("exec", {"command": "git push origin main"})
    graph = action.as_rdf_graph()
    assert len(graph) > 0

    # Verify correct rdf:type triple
    type_triples = list(graph.triples((None, RDF.type, SC["GitPush"])))
    assert len(type_triples) == 1

    action_node = type_triples[0][0]

    # Verify risk level
    risk_triples = list(graph.triples((action_node, SC.hasRiskLevel, SC["HighRisk"])))
    assert len(risk_triples) == 1

    # Verify isReversible
    reversible_triples = list(graph.triples((action_node, SC.isReversible, None)))
    assert len(reversible_triples) == 1

    # Verify affectsScope
    scope_triples = list(graph.triples((action_node, SC.affectsScope, SC["SharedState"])))
    assert len(scope_triples) == 1
