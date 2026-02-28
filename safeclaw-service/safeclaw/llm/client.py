"""Mistral client wrapper with timeout, error handling, and graceful degradation."""

import asyncio
import json
import logging

from safeclaw.config import SafeClawConfig

logger = logging.getLogger("safeclaw.llm")


class SafeClawLLMClient:
    """Thin wrapper around the Mistral SDK with timeout and error handling."""

    def __init__(self, mistral_client, model: str, model_large: str, timeout_ms: int):
        self._client = mistral_client
        self.model = model
        self.model_large = model_large
        self.timeout_ms = timeout_ms

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> str | None:
        """Send a chat completion request. Returns content string or None on failure."""
        try:
            response = await asyncio.wait_for(
                self._client.chat.complete_async(
                    model=model or self.model,
                    messages=messages,
                    temperature=temperature,
                ),
                timeout=self.timeout_ms / 1000,
            )
            return response.choices[0].message.content
        except asyncio.TimeoutError:
            logger.warning("LLM request timed out after %dms", self.timeout_ms)
            return None
        except Exception:
            logger.warning("LLM request failed", exc_info=True)
            return None

    async def chat_json(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> dict | None:
        """Send a chat request and parse the response as JSON. Returns dict or None."""
        content = await self.chat(messages, model=model, temperature=temperature)
        if content is None:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("LLM response was not valid JSON: %s", content[:200])
            return None


def create_client(config: SafeClawConfig) -> SafeClawLLMClient | None:
    """Create a SafeClawLLMClient from config. Returns None if no API key."""
    if not config.mistral_api_key:
        return None
    try:
        from mistralai import Mistral

        mistral = Mistral(api_key=config.mistral_api_key)
        return SafeClawLLMClient(
            mistral_client=mistral,
            model=config.mistral_model,
            model_large=config.mistral_model_large,
            timeout_ms=config.mistral_timeout_ms,
        )
    except Exception:
        logger.warning("Failed to initialize Mistral client", exc_info=True)
        return None
