"""Hybrid engine - routes between local cache and remote SafeClaw service."""

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from safeclaw.engine.core import (
    AgentStartEvent,
    ContextResult,
    Decision,
    LlmIOEvent,
    MessageEvent,
    SafeClawEngine,
    ToolCallEvent,
    ToolResultEvent,
)

logger = logging.getLogger("safeclaw.hybrid")


@dataclass
class CircuitBreakerState:
    """Tracks remote service availability with half-open state."""
    failures: int = 0
    max_failures: int = 3
    last_failure: float = 0
    recovery_timeout: float = 60.0  # seconds
    is_open: bool = False
    _probe_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _probing: bool = False

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure = time.monotonic()
        self._probing = False
        if self.failures >= self.max_failures:
            self.is_open = True
            logger.warning("Circuit breaker OPEN: switching to local-only mode")

    def record_success(self) -> None:
        self.failures = 0
        self._probing = False
        if self.is_open:
            self.is_open = False
            logger.info("Circuit breaker CLOSED: remote service recovered")

    async def should_try_remote(self) -> bool:
        if not self.is_open:
            return True
        # Half-open: allow one probe request after recovery timeout
        if time.monotonic() - self.last_failure > self.recovery_timeout:
            if self._probe_lock.locked():
                return False  # Another request is already probing
            async with self._probe_lock:
                if self._probing:
                    return False
                self._probing = True
                return True
        return False


class HybridEngine(SafeClawEngine):
    """Routes constraint checks between local cache and remote SafeClaw service.

    When the remote service is available, it handles complex checks.
    When unavailable (circuit breaker open), falls back to local-only mode.
    """

    def __init__(
        self,
        remote_url: str,
        api_key: str,
        local_engine: SafeClawEngine | None = None,
        timeout: float = 0.5,
    ):
        self.remote_url = remote_url.rstrip("/")
        self.api_key = api_key
        self.local_engine = local_engine
        self.timeout = timeout
        self.circuit_breaker = CircuitBreakerState()
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def close(self) -> None:
        """Close the shared HTTP client."""
        await self._client.aclose()

    async def evaluate_tool_call(self, event: ToolCallEvent) -> Decision:
        if await self.circuit_breaker.should_try_remote():
            try:
                resp = await self._client.post(
                    f"{self.remote_url}/api/v1/evaluate/tool-call",
                    json={
                        "sessionId": event.session_id,
                        "userId": event.user_id,
                        "agentId": event.agent_id,
                        "agentToken": event.agent_token,
                        "toolName": event.tool_name,
                        "params": event.params,
                        "sessionHistory": event.session_history,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                self.circuit_breaker.record_success()
                return Decision(
                    block=data["block"],
                    reason=data.get("reason", ""),
                    audit_id=data.get("auditId", ""),
                )
            except Exception as e:
                logger.warning(f"Remote service error: {e}")
                self.circuit_breaker.record_failure()

        # Fallback to local engine
        if self.local_engine:
            return await self.local_engine.evaluate_tool_call(event)
        return Decision(block=False)

    async def evaluate_message(self, event: MessageEvent) -> Decision:
        if await self.circuit_breaker.should_try_remote():
            try:
                resp = await self._client.post(
                    f"{self.remote_url}/api/v1/evaluate/message",
                    json={
                        "sessionId": event.session_id,
                        "userId": event.user_id,
                        "agentId": event.agent_id,
                        "agentToken": event.agent_token,
                        "to": event.to,
                        "content": event.content,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                self.circuit_breaker.record_success()
                return Decision(
                    block=data["block"],
                    reason=data.get("reason", ""),
                    audit_id=data.get("auditId", ""),
                )
            except Exception as e:
                logger.warning(f"Remote service error: {e}")
                self.circuit_breaker.record_failure()

        if self.local_engine:
            return await self.local_engine.evaluate_message(event)
        return Decision(block=False)

    async def build_context(self, event: AgentStartEvent) -> ContextResult:
        if await self.circuit_breaker.should_try_remote():
            try:
                resp = await self._client.post(
                    f"{self.remote_url}/api/v1/context/build",
                    json={
                        "sessionId": event.session_id,
                        "userId": event.user_id,
                        "agentId": event.agent_id,
                        "agentToken": event.agent_token,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                self.circuit_breaker.record_success()
                return ContextResult(prepend_context=data.get("prependContext", ""))
            except Exception as e:
                logger.warning(f"Remote service error: {e}")
                self.circuit_breaker.record_failure()

        if self.local_engine:
            return await self.local_engine.build_context(event)
        return ContextResult()

    async def record_action_result(self, event: ToolResultEvent) -> None:
        # Fire-and-forget to remote, also record locally
        if await self.circuit_breaker.should_try_remote():
            try:
                await self._client.post(
                    f"{self.remote_url}/api/v1/record/tool-result",
                    json={
                        "sessionId": event.session_id,
                        "agentId": event.agent_id,
                        "agentToken": event.agent_token,
                        "toolName": event.tool_name,
                        "params": event.params,
                        "result": event.result,
                        "success": event.success,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to record action result remotely: {e}")

        if self.local_engine:
            await self.local_engine.record_action_result(event)

    async def log_llm_io(self, event: LlmIOEvent) -> None:
        if self.local_engine:
            await self.local_engine.log_llm_io(event)
