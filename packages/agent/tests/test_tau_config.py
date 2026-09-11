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


def test_ensure_catalog_entry_calls_write_when_needed(monkeypatch):
    from agent.tau_config import ensure_catalog_entry

    monkeypatch.setenv("LLM_API_KEY", "sk-custom")
    monkeypatch.setenv("LLM_BASE_URL", "https://custom.api/v1")
    monkeypatch.setenv("LLM_MODEL", "custom-model")

    written = []
    monkeypatch.setattr("agent.tau_config.write_catalog_entry", lambda target: written.append(target))

    ensure_catalog_entry()
    assert len(written) == 1
    assert written[0].model == "custom-model"


def test_gemini_model_selects_native_google_provider(monkeypatch):
    """Gemini models route to native google provider and bridge LLM_API_KEY to GEMINI_API_KEY."""
    monkeypatch.setenv("LLM_API_KEY", "AIzaSy-test")
    monkeypatch.setenv("LLM_MODEL", "gemini-3-flash-preview")
    monkeypatch.setenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")

    target = resolve_provider()

    assert target.provider == "google"
    assert target.model == "gemini-3-flash-preview"
    assert target.needs_catalog_entry is False
    assert target.provider_key_env == "GEMINI_API_KEY"
    assert target.credential_env() == {"GEMINI_API_KEY": "AIzaSy-test"}


def test_explicit_google_provider_with_gemini_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy-direct")
    monkeypatch.setenv("LLM_MODEL", "gemini-flash-latest")

    target = resolve_provider()

    assert target.provider == "google"
    assert target.model == "gemini-flash-latest"
    assert target.needs_catalog_entry is False
    assert target.provider_key_env == "GEMINI_API_KEY"
    assert target.credential_env() == {}


def test_ensure_catalog_entry_registers_unlisted_google_model(monkeypatch):
    from agent.tau_config import ensure_catalog_entry

    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy-direct")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.8-flash")

    registered = []
    monkeypatch.setattr("agent.tau_config.ensure_google_model_registered", lambda model: registered.append(model))

    ensure_catalog_entry()
    assert registered == ["gemini-3.8-flash"]


def test_claude_model_infers_native_anthropic_provider(monkeypatch):
    """Claude models route to native anthropic provider and bridge LLM_API_KEY to ANTHROPIC_API_KEY."""
    monkeypatch.setenv("LLM_API_KEY", "sk-ant-generic")
    monkeypatch.setenv("LLM_MODEL", "claude-3-7-sonnet-20250219")

    target = resolve_provider()

    assert target.provider == "anthropic"
    assert target.model == "claude-3-7-sonnet-20250219"
    assert target.needs_catalog_entry is False
    assert target.provider_key_env == "ANTHROPIC_API_KEY"
    assert target.credential_env() == {"ANTHROPIC_API_KEY": "sk-ant-generic"}


def test_explicit_anthropic_provider_with_llm_api_key_bridging(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-ant-bridge")

    target = resolve_provider()

    assert target.provider == "anthropic"
    assert target.model == "claude-sonnet-4-6"
    assert target.needs_catalog_entry is False
    assert target.provider_key_env == "ANTHROPIC_API_KEY"
    assert target.credential_env() == {"ANTHROPIC_API_KEY": "sk-ant-bridge"}


def test_ensure_catalog_entry_registers_unlisted_anthropic_model(monkeypatch):
    from agent.tau_config import ensure_catalog_entry

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-direct")
    monkeypatch.setenv("LLM_MODEL", "claude-3-7-sonnet-20250219")

    registered = []
    monkeypatch.setattr("agent.tau_config.ensure_anthropic_model_registered", lambda model: registered.append(model))

    ensure_catalog_entry()
    assert registered == ["claude-3-7-sonnet-20250219"]




