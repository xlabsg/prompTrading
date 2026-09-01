from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    temperature: float
    provider: str


def _maybe_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return value


def load_llm_config() -> LLMConfig:
    """
    Resolve OpenAI-compatible LLM configuration from env vars.

    Priority:
    - Generic vars: LLM_*
    - Provider-specific fallback: DEEPSEEK_*, OPENAI_API_KEY/GEMINI_API_KEY
    """
    provider = (_maybe_env("LLM_PROVIDER") or "").strip().lower()
    if not provider:
        provider = "deepseek" if _maybe_env("DEEPSEEK_API_KEY") else "openai"

    api_key = _maybe_env("LLM_API_KEY")
    base_url = _maybe_env("LLM_BASE_URL")
    model = _maybe_env("LLM_MODEL")
    temperature_raw = _maybe_env("LLM_TEMPERATURE")

    if not api_key:
        if provider == "deepseek":
            api_key = _maybe_env("DEEPSEEK_API_KEY")
        else:
            api_key = _maybe_env("OPENAI_API_KEY") or _maybe_env("GEMINI_API_KEY")

    if not base_url:
        if provider == "deepseek":
            base_url = _maybe_env("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
        elif provider == "gemini":
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        else:
            base_url = "https://api.openai.com/v1"

    if not model:
        if provider == "deepseek":
            model = _maybe_env("DEEPSEEK_MODEL") or "deepseek-chat"
        elif provider == "gemini":
            model = "gemini-1.5-flash"
        else:
            model = "gpt-4o-mini"

    temperature = float(temperature_raw) if temperature_raw else 0.2

    return LLMConfig(
        api_key=api_key or "",
        base_url=base_url or "",
        model=model or "",
        temperature=temperature,
        provider=provider,
    )
