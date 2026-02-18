"""Phase 5 tests: API key authentication, middleware, hybrid engine, circuit breaker."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from safeclaw.auth.api_key import APIKey, APIKeyManager
from safeclaw.engine.hybrid_engine import CircuitBreakerState, HybridEngine
from safeclaw.engine.core import (
    AgentStartEvent,
    ContextResult,
    Decision,
    LlmIOEvent,
    MessageEvent,
    ToolCallEvent,
    ToolResultEvent,
)


# --- APIKeyManager Tests ---

class TestAPIKeyManager:
    def test_create_key_returns_raw_and_record(self):
        mgr = APIKeyManager()
        raw_key, api_key = mgr.create_key("org-1")
        assert raw_key.startswith("sc_")
        assert api_key.org_id == "org-1"
        assert api_key.scope == "full"
        assert api_key.is_active is True

    def test_create_key_custom_scope(self):
        mgr = APIKeyManager()
        raw_key, api_key = mgr.create_key("org-1", scope="read_only")
        assert api_key.scope == "read_only"

    def test_validate_key_success(self):
        mgr = APIKeyManager()
        raw_key, api_key = mgr.create_key("org-1")
        validated = mgr.validate_key(raw_key)
        assert validated is not None
        assert validated.org_id == "org-1"
        assert validated.key_id == api_key.key_id

    def test_validate_key_wrong_key(self):
        mgr = APIKeyManager()
        mgr.create_key("org-1")
        result = mgr.validate_key("sc_totally_wrong_key_here_12345678")
        assert result is None

    def test_validate_key_nonexistent(self):
        mgr = APIKeyManager()
        result = mgr.validate_key("sc_nonexistent_key")
        assert result is None

    def test_revoke_key(self):
        mgr = APIKeyManager()
        raw_key, api_key = mgr.create_key("org-1")
        assert mgr.revoke_key(api_key.key_id) is True
        # Revoked key should not validate
        assert mgr.validate_key(raw_key) is None

    def test_revoke_nonexistent_key(self):
        mgr = APIKeyManager()
        assert mgr.revoke_key("nonexistent") is False

    def test_list_keys_filters_by_org(self):
        mgr = APIKeyManager()
        mgr.create_key("org-1")
        mgr.create_key("org-1")
        mgr.create_key("org-2")
        assert len(mgr.list_keys("org-1")) == 2
        assert len(mgr.list_keys("org-2")) == 1
        assert len(mgr.list_keys("org-3")) == 0

    def test_generate_key_uniqueness(self):
        keys = set()
        for _ in range(50):
            raw_key, key_id = APIKeyManager.generate_key()
            keys.add(raw_key)
        assert len(keys) == 50

    def test_hash_key_deterministic(self):
        h1 = APIKeyManager.hash_key("sc_test_key")
        h2 = APIKeyManager.hash_key("sc_test_key")
        assert h1 == h2

    def test_hash_key_different_for_different_keys(self):
        h1 = APIKeyManager.hash_key("sc_key_a")
        h2 = APIKeyManager.hash_key("sc_key_b")
        assert h1 != h2


# --- APIKeyAuthMiddleware Tests ---

class TestAPIKeyAuthMiddleware:
    """Tests for the auth middleware using mocked ASGI components."""

    def test_skip_health_path(self):
        from safeclaw.auth.middleware import APIKeyAuthMiddleware

        app = MagicMock()
        middleware = APIKeyAuthMiddleware(app, api_key_manager=MagicMock(), require_auth=True)
        assert "/api/v1/health" in middleware.SKIP_PATHS
        assert "/docs" in middleware.SKIP_PREFIXES

    def test_auth_disabled_passes_through(self):
        from safeclaw.auth.middleware import APIKeyAuthMiddleware

        app = MagicMock()
        middleware = APIKeyAuthMiddleware(app, api_key_manager=None, require_auth=False)
        # require_auth is False, so it should pass through
        assert middleware.require_auth is False


# --- CircuitBreakerState Tests ---

class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        cb = CircuitBreakerState()
        assert cb.is_open is False
        assert cb.failures == 0
        assert await cb.should_try_remote() is True

    @pytest.mark.asyncio
    async def test_opens_after_max_failures(self):
        cb = CircuitBreakerState(max_failures=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is False
        cb.record_failure()
        assert cb.is_open is True
        assert await cb.should_try_remote() is False

    def test_closes_on_success(self):
        cb = CircuitBreakerState(max_failures=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        cb.record_success()
        assert cb.is_open is False
        assert cb.failures == 0

    @pytest.mark.asyncio
    async def test_recovery_timeout_allows_retry(self, monkeypatch):
        fake_time = [1000.0]
        monkeypatch.setattr("time.monotonic", lambda: fake_time[0])
        cb = CircuitBreakerState(max_failures=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.is_open is True
        assert await cb.should_try_remote() is False
        # Advance past recovery timeout
        fake_time[0] += 0.15
        assert await cb.should_try_remote() is True

    def test_partial_failures_dont_open(self):
        cb = CircuitBreakerState(max_failures=3)
        cb.record_failure()
        cb.record_failure()
        # Success resets counter
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is False


# --- HybridEngine Tests ---

def _make_local_engine(**overrides):
    """Create a mock local engine with async methods."""
    engine = AsyncMock()
    engine.evaluate_tool_call.return_value = Decision(block=False)
    engine.evaluate_message.return_value = Decision(block=False)
    engine.build_context.return_value = ContextResult()
    engine.record_action_result.return_value = None
    engine.log_llm_io.return_value = None
    for key, val in overrides.items():
        getattr(engine, key).return_value = val
    return engine


def _make_hybrid(local_engine=None, circuit_open=True):
    """Create a HybridEngine with circuit breaker open (local-only mode)."""
    engine = HybridEngine(
        remote_url="http://localhost:99999",
        api_key="sc_test",
        local_engine=local_engine,
        timeout=0.1,
    )
    if circuit_open:
        engine.circuit_breaker.is_open = True
        engine.circuit_breaker.last_failure = time.monotonic()
    return engine


class TestHybridEngine:
    @pytest.mark.asyncio
    async def test_evaluate_tool_call_local_fallback_when_no_remote(self):
        """When remote fails, falls back to local engine."""
        local = _make_local_engine(evaluate_tool_call=Decision(block=False, reason="local"))
        engine = _make_hybrid(local_engine=local)

        event = ToolCallEvent(
            session_id="s1", user_id="u1", tool_name="Bash", params={"command": "ls"}
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False
        assert decision.reason == "local"
        local.evaluate_tool_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_tool_call_no_local_no_remote_fail_closed(self):
        """When both remote and local are unavailable, fails closed by default."""
        engine = _make_hybrid(local_engine=None)

        event = ToolCallEvent(
            session_id="s1", user_id="u1", tool_name="Bash", params={"command": "ls"}
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is True
        assert "unavailable" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_evaluate_tool_call_no_local_no_remote_fail_open(self):
        """When fail_closed=False, allows actions when service is unavailable."""
        engine = HybridEngine(
            remote_url="http://localhost:99999",
            api_key="sc_test",
            local_engine=None,
            timeout=0.1,
            fail_closed=False,
        )
        engine.circuit_breaker.is_open = True
        engine.circuit_breaker.last_failure = time.monotonic()

        event = ToolCallEvent(
            session_id="s1", user_id="u1", tool_name="Bash", params={"command": "ls"}
        )
        decision = await engine.evaluate_tool_call(event)
        assert decision.block is False

    @pytest.mark.asyncio
    async def test_evaluate_message_local_fallback(self):
        local = _make_local_engine(evaluate_message=Decision(block=True, reason="blocked locally"))
        engine = _make_hybrid(local_engine=local)

        event = MessageEvent(session_id="s1", user_id="u1", to="bob", content="hi")
        decision = await engine.evaluate_message(event)
        assert decision.block is True
        assert decision.reason == "blocked locally"

    @pytest.mark.asyncio
    async def test_build_context_local_fallback(self):
        local = _make_local_engine(build_context=ContextResult(prepend_context="local ctx"))
        engine = _make_hybrid(local_engine=local)

        event = AgentStartEvent(session_id="s1", user_id="u1")
        result = await engine.build_context(event)
        assert result.prepend_context == "local ctx"

    @pytest.mark.asyncio
    async def test_record_action_result_local(self):
        local = _make_local_engine()
        engine = _make_hybrid(local_engine=local)

        event = ToolResultEvent(
            session_id="s1", tool_name="Bash", params={}, result="ok", success=True
        )
        await engine.record_action_result(event)
        local.record_action_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_llm_io_delegates_to_local(self):
        local = _make_local_engine()
        engine = _make_hybrid(local_engine=local, circuit_open=False)

        event = LlmIOEvent(session_id="s1", direction="input", content="hello")
        await engine.log_llm_io(event)
        local.log_llm_io.assert_called_once()

    @pytest.mark.asyncio
    async def test_remote_failure_opens_circuit_breaker(self):
        """Repeated remote failures should open the circuit breaker."""
        engine = _make_hybrid(local_engine=None, circuit_open=False)

        event = ToolCallEvent(
            session_id="s1", user_id="u1", tool_name="Bash", params={"command": "ls"}
        )

        # Mock the HTTP client to raise ConnectError immediately
        async def _raise_connect_error(*args, **kwargs):
            raise httpx.ConnectError("mocked connection refused")

        engine._client.post = _raise_connect_error

        # Make 3 calls that will fail
        for _ in range(3):
            await engine.evaluate_tool_call(event)

        assert engine.circuit_breaker.failures >= 3
        assert engine.circuit_breaker.is_open is True
