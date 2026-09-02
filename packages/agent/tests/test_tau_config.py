"""Provider resolution: which Tau provider runs, and where its key comes from."""

from __future__ import annotations

import pytest

from agent.tau_config import resolve_provider

_LLM_ENV = (
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in _LLM_ENV:
        monkeypatch.delenv(name, raising=False)


def test_anthropic_key_selects_the_native_provider(monkeypatch):
    """Native anthropic is what makes prompt caching available."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")

    target = resolve_provider()

    assert target.provider == "anthropic"
    assert target.needs_catalog_entry is False
    assert target.provider_key_env == "ANTHROPIC_API_KEY"


def test_builtin_provider_needs_no_catalog_entry(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")

    target = resolve_provider()

    assert target.provider == "deepseek"
    assert target.needs_catalog_entry is False


def test_platform_key_is_republished_under_the_provider_name(monkeypatch):
    """LLM_API_KEY is this platform's name for the key; Tau reads its own."""
    monkeypatch.setenv("LLM_API_KEY", "sk-platform")

    target = resolve_provider()

    assert target.api_key_env == "LLM_API_KEY"
    assert target.provider_key_env == "OPENAI_API_KEY"
    assert target.credential_env() == {"OPENAI_API_KEY": "sk-platform"}


def test_no_bridging_when_the_names_already_agree(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    assert resolve_provider().credential_env() == {}


def test_custom_base_url_becomes_a_catalog_entry(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-gateway")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.internal/v1")
    monkeypatch.setenv("LLM_MODEL", "some-model")

    target = resolve_provider()

    assert target.needs_catalog_entry is True
    assert target.base_url == "https://gateway.internal/v1"
    assert target.model == "some-model"
    # The entry we write names LLM_API_KEY itself, so nothing needs bridging.
    assert target.provider_key_env == "LLM_API_KEY"
    assert target.credential_env() == {}


def test_provider_default_base_url_is_not_custom(monkeypatch):
    """Pointing at the provider's own endpoint must not fork the catalog."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")

    assert resolve_provider().needs_catalog_entry is False
