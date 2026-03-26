"""Tests for engine-level input sanitization (#136).

Verifies that FullEngine.evaluate_tool_call() sanitizes tool_name and params
even when called directly (bypassing the API route layer).
"""

import pytest
from pathlib import Path

from safeclaw.config import SafeClawConfig
from safeclaw.engine.core import ToolCallEvent
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def engine(tmp_path):
    """Create a test engine with ontologies from the project."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
    )
    return FullEngine(config)


@pytest.mark.asyncio
async def test_tool_name_control_chars_stripped(engine):
    """Control characters in tool_name are stripped before evaluation."""
    event = ToolCallEvent(
        session_id="test-sanitize",
        user_id="test-user",
        tool_name="read\x00\x01\x07",
        params={"file_path": "/src/main.py"},
    )
    decision = await engine.evaluate_tool_call(event)
    # After sanitization, tool_name should be "read" (control chars removed).
    # The event object is mutated in-place by evaluate_tool_call.
    assert event.tool_name == "read"
    # A simple read should be allowed
    assert decision.block is False


@pytest.mark.asyncio
async def test_params_control_chars_stripped(engine):
    """Control characters in param values are stripped before evaluation."""
    event = ToolCallEvent(
        session_id="test-sanitize",
        user_id="test-user",
        tool_name="read",
        params={"file_path": "/src/main\x00.py"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert event.params["file_path"] == "/src/main.py"
    assert decision.block is False


@pytest.mark.asyncio
async def test_nested_params_sanitized(engine):
    """Nested dict/list params are recursively sanitized."""
    event = ToolCallEvent(
        session_id="test-sanitize",
        user_id="test-user",
        tool_name="read",
        params={
            "file_path": "/src/main.py",
            "options": {"encoding": "utf\x008"},
            "tags": ["alpha\x01", "beta"],
        },
    )
    await engine.evaluate_tool_call(event)
    assert event.params["options"]["encoding"] == "utf8"
    assert event.params["tags"] == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_empty_params_handled(engine):
    """Empty params dict should not cause errors."""
    event = ToolCallEvent(
        session_id="test-sanitize",
        user_id="test-user",
        tool_name="read",
        params={},
    )
    decision = await engine.evaluate_tool_call(event)
    assert event.params == {}
    # read with no file_path may or may not be blocked by other checks,
    # but the sanitization step should not raise
    assert isinstance(decision.block, bool)


@pytest.mark.asyncio
async def test_param_keys_sanitized(engine):
    """Control characters in param keys are also stripped."""
    event = ToolCallEvent(
        session_id="test-sanitize",
        user_id="test-user",
        tool_name="read",
        params={"file\x00_path": "/src/main.py"},
    )
    await engine.evaluate_tool_call(event)
    # The key should have the null byte stripped
    assert "file_path" in event.params
    assert "\x00" not in str(event.params)


@pytest.mark.asyncio
async def test_sanitization_is_idempotent(engine):
    """Calling evaluate_tool_call with already-clean input is a no-op."""
    event = ToolCallEvent(
        session_id="test-sanitize",
        user_id="test-user",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )
    await engine.evaluate_tool_call(event)
    assert event.tool_name == "read"
    assert event.params == {"file_path": "/src/main.py"}
