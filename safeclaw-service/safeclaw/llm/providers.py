"""LLM provider registry — metadata for OpenAI-compatible providers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    base_url: str
    default_model: str
    default_model_large: str
    key_placeholder: str
    console_url: str
    free_tier: str  # "Yes", "No", "Limited free", "$5 free credit", etc.


PROVIDERS: dict[str, ProviderInfo] = {
    "mistral": ProviderInfo(
        id="mistral",
        name="Mistral",
        base_url="https://api.mistral.ai/v1",
        default_model="mistral-small-latest",
        default_model_large="mistral-large-latest",
        key_placeholder="Enter your Mistral API key",
        console_url="https://console.mistral.ai",
        free_tier="Yes",
    ),
    "openai": ProviderInfo(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        default_model_large="gpt-4o",
        key_placeholder="sk-...",
        console_url="https://platform.openai.com",
        free_tier="No",
    ),
    "gemini": ProviderInfo(
        id="gemini",
        name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-2.0-flash",
        default_model_large="gemini-2.5-pro",
        key_placeholder="AIza...",
        console_url="https://aistudio.google.com",
        free_tier="Yes",
    ),
    "groq": ProviderInfo(
        id="groq",
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        default_model_large="llama-3.3-70b-versatile",
        key_placeholder="gsk_...",
        console_url="https://console.groq.com",
        free_tier="Yes",
    ),
    "xai": ProviderInfo(
        id="xai",
        name="xAI / Grok",
        base_url="https://api.x.ai/v1",
        default_model="grok-2-latest",
        default_model_large="grok-2-latest",
        key_placeholder="xai-...",
        console_url="https://console.x.ai",
        free_tier="No",
    ),
    "deepseek": ProviderInfo(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        default_model_large="deepseek-chat",
        key_placeholder="sk-...",
        console_url="https://platform.deepseek.com",
        free_tier="No",
    ),
    "kimi": ProviderInfo(
        id="kimi",
        name="Kimi (Moonshot)",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k",
        default_model_large="moonshot-v1-32k",
        key_placeholder="sk-...",
        console_url="https://platform.moonshot.cn",
        free_tier="Limited free",
    ),
    "qwen": ProviderInfo(
        id="qwen",
        name="Qwen (Alibaba)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        default_model_large="qwen-max",
        key_placeholder="sk-...",
        console_url="https://dashscope.console.aliyun.com",
        free_tier="Yes",
    ),
    "together": ProviderInfo(
        id="together",
        name="Together AI",
        base_url="https://api.together.xyz/v1",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        default_model_large="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        key_placeholder="...",
        console_url="https://api.together.xyz",
        free_tier="$5 free credit",
    ),
    "openrouter": ProviderInfo(
        id="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="openrouter/auto",
        default_model_large="openrouter/auto",
        key_placeholder="sk-or-...",
        console_url="https://openrouter.ai",
        free_tier="Some free models",
    ),
    "custom": ProviderInfo(
        id="custom",
        name="Custom (OpenAI-compatible)",
        base_url="",
        default_model="",
        default_model_large="",
        key_placeholder="Optional",
        console_url="",
        free_tier="",
    ),
}
