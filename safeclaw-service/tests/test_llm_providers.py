"""Tests for the LLM provider registry."""

from safeclaw.llm.providers import PROVIDERS, ProviderInfo


def test_provider_info_is_frozen_dataclass():
    """ProviderInfo instances are immutable."""
    info = PROVIDERS["mistral"]
    assert isinstance(info, ProviderInfo)
    try:
        info.name = "changed"
        assert False, "Should not be able to mutate frozen dataclass"
    except AttributeError:
        pass


def test_all_ten_named_providers_exist():
    """All 10 named providers are in the registry."""
    expected = {
        "mistral",
        "openai",
        "gemini",
        "groq",
        "xai",
        "deepseek",
        "kimi",
        "qwen",
        "together",
        "openrouter",
    }
    assert expected == {k for k in PROVIDERS if k != "custom"}


def test_custom_provider_exists():
    """Custom provider entry exists with empty base_url."""
    assert "custom" in PROVIDERS
    assert PROVIDERS["custom"].base_url == ""


def test_every_provider_has_required_fields():
    """Every provider has non-empty name, default_model, and console_url (except custom)."""
    for pid, info in PROVIDERS.items():
        assert info.id == pid, f"Provider {pid} id mismatch"
        assert info.name, f"Provider {pid} missing name"
        if pid != "custom":
            assert info.default_model, f"Provider {pid} missing default_model"
        if pid != "custom":
            assert info.base_url, f"Provider {pid} missing base_url"
            assert info.console_url, f"Provider {pid} missing console_url"


def test_provider_base_urls_end_correctly():
    """Base URLs should end with /v1 or similar versioned path (not trailing slash)."""
    for pid, info in PROVIDERS.items():
        if pid == "custom":
            continue
        assert not info.base_url.endswith(
            "/"
        ), f"Provider {pid} base_url should not end with slash: {info.base_url}"
