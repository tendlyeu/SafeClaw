"""Tests for the NL → Policy Compiler."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from safeclaw.engine.knowledge_graph import KnowledgeGraph


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.chat = AsyncMock()
    client.model_large = "mistral-large-latest"
    return client


@pytest.fixture
def kg():
    kg = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    kg.load_directory(ontology_dir)
    return kg


VALID_TURTLE = """\
sp:NoProdDeploy a sp:Prohibition, sp:CommandConstraint ;
    sp:forbiddenCommandPattern "deploy.*production" ;
    sp:reason "Deploying to production is forbidden without approval" ;
    rdfs:label "No production deploy" .
"""


@pytest.mark.asyncio
async def test_compile_valid_policy(mock_llm_client, kg):
    """compile() returns success with valid generated Turtle."""
    from safeclaw.llm.policy_compiler import PolicyCompiler

    mock_llm_client.chat.return_value = VALID_TURTLE

    compiler = PolicyCompiler(mock_llm_client, kg)
    result = await compiler.compile("Never deploy to production without approval")

    assert result.success is True
    assert "NoProdDeploy" in result.turtle
    assert result.policy_name == "NoProdDeploy"
    assert len(result.validation_errors) == 0


@pytest.mark.asyncio
async def test_compile_invalid_turtle_syntax(mock_llm_client, kg):
    """compile() returns failure on invalid Turtle syntax."""
    from safeclaw.llm.policy_compiler import PolicyCompiler

    mock_llm_client.chat.return_value = "this is not valid turtle at all {"

    compiler = PolicyCompiler(mock_llm_client, kg)
    result = await compiler.compile("Some policy")

    assert result.success is False
    assert len(result.validation_errors) > 0


@pytest.mark.asyncio
async def test_compile_missing_reason(mock_llm_client, kg):
    """compile() flags policies without sp:reason."""
    from safeclaw.llm.policy_compiler import PolicyCompiler

    no_reason_turtle = """\
sp:BadPolicy a sp:Prohibition, sp:CommandConstraint ;
    sp:forbiddenCommandPattern "bad" ;
    rdfs:label "Bad policy" .
"""
    mock_llm_client.chat.return_value = no_reason_turtle

    compiler = PolicyCompiler(mock_llm_client, kg)
    result = await compiler.compile("Block bad things")

    assert result.success is False
    assert any("reason" in e.lower() for e in result.validation_errors)


@pytest.mark.asyncio
async def test_compile_llm_timeout(mock_llm_client, kg):
    """compile() returns failure on LLM timeout."""
    from safeclaw.llm.policy_compiler import PolicyCompiler

    mock_llm_client.chat.return_value = None

    compiler = PolicyCompiler(mock_llm_client, kg)
    result = await compiler.compile("Some policy")

    assert result.success is False
    assert any("llm" in e.lower() or "timeout" in e.lower() for e in result.validation_errors)
