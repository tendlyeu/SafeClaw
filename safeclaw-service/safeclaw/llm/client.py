"""OpenAI-compatible LLM client with timeout, error handling, and backward compat."""

import asyncio
import json
import logging

from openai import AsyncOpenAI

from safeclaw.config import SafeClawConfig
from safeclaw.llm.providers import PROVIDERS

logger = logging.getLogger("safeclaw.llm")


class SafeClawLLMClient:
    """Thin wrapper around the OpenAI SDK with timeout and error handling."""

    def __init__(self, openai_client: AsyncOpenAI, model: str, model_large: str, timeout_ms: int):
        self._client = openai_client
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
                self._client.chat.completions.create(
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


def _resolve_llm_config(
    config: SafeClawConfig,
) -> tuple[str, str, str, str, str] | None:
    """Resolve provider, key, models, and base_url from config.

    Priority:
    1. llm_provider set -> use llm_* fields
    2. mistral_api_key set -> backward compat with Mistral
    3. Neither -> return None

    Returns (provider_id, api_key, model, model_large, base_url) or None.
    """
    if config.llm_provider:
        provider_id = config.llm_provider
        if provider_id not in PROVIDERS:
            logger.warning("Unknown LLM provider: %s", provider_id)
            return None
        info = PROVIDERS[provider_id]

        api_key = config.llm_api_key
        if not api_key and provider_id != "custom":
            return None

        base_url = config.llm_base_url if provider_id == "custom" else info.base_url
        if provider_id == "custom" and not base_url:
            return None

        model = config.llm_model or info.default_model
        model_large = config.llm_model_large or info.default_model_large

        # Custom with no key: use placeholder (Ollama etc. don't need real keys)
        if not api_key:
            api_key = "unused"

        return (provider_id, api_key, model, model_large, base_url)

    # Legacy fallback
    if config.mistral_api_key:
        info = PROVIDERS["mistral"]
        return (
            "mistral",
            config.mistral_api_key,
            config.mistral_model,
            config.mistral_model_large,
            info.base_url,
        )

    return None


def create_client(config: SafeClawConfig) -> SafeClawLLMClient | None:
    """Create a SafeClawLLMClient from config. Returns None if no provider configured."""
    resolved = _resolve_llm_config(config)
    if resolved is None:
        return None

    provider_id, api_key, model, model_large, base_url = resolved

    # Determine timeout: prefer llm_timeout_ms if new-style config, else legacy
    if config.llm_provider:
        timeout_ms = config.llm_timeout_ms
    else:
        timeout_ms = config.mistral_timeout_ms

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        return SafeClawLLMClient(
            openai_client=client,
            model=model,
            model_large=model_large,
            timeout_ms=timeout_ms,
        )
    except Exception:
        logger.warning(
            "Failed to initialize LLM client for provider %s", provider_id, exc_info=True
        )
        return None
