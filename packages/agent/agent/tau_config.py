"""Map this platform's LLM environment variables onto a Tau provider.

Tau ships a provider catalog covering ~28 providers, including native
`anthropic` (the `anthropic-messages` API, which is what makes prompt caching
available) and native `deepseek`. Those need no configuration beyond their API
key, so the common case here resolves to a provider name and a model id.

The one case that needs a file written is a custom `LLM_BASE_URL` -- a gateway
or a relay -- which becomes an OpenAI-compatible catalog entry. Writing it is a
pure local file operation, so it runs at image build time.

Run as a module (`python -m agent.tau_config`) to write that entry; import
`resolve_provider()` to learn which provider and model to launch Tau with.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# The provider name `setup_command` writes to, and the one the driver passes to
# `--provider` whenever a custom base URL is configured.
CUSTOM_PROVIDER_NAME = "custom_openai"

_DEFAULT_BASE_URLS = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
}


# What each built-in Tau provider reads its key from. This platform's own env
# vars (LLM_API_KEY, DEEPSEEK_API_KEY, ...) do not have to agree with these, so
# `credential_env()` bridges the two.
_PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
}


@dataclass(frozen=True)
class TauProvider:
    """Which Tau provider and model this container should run."""

    provider: str
    model: str
    api_key_env: str
    base_url: str | None = None

    @property
    def needs_catalog_entry(self) -> bool:
        """Whether Tau has to be told about this provider before it can be used."""
        return self.base_url is not None

    @property
    def provider_key_env(self) -> str:
        """The environment variable Tau itself reads the API key from.

        A catalog entry we write names `api_key_env` directly. A built-in
        provider names its own, which is why a platform key supplied under
        `LLM_API_KEY` has to be republished under the provider's name.
        """
        if self.needs_catalog_entry:
            return self.api_key_env
        return _PROVIDER_KEY_ENV.get(self.provider, "OPENAI_API_KEY")

    def credential_env(self) -> dict[str, str]:
        """Environment to add to the Tau child so it can find the API key."""
        key = os.getenv(self.api_key_env)
        if not key or self.provider_key_env == self.api_key_env:
            return {}
        return {self.provider_key_env: key}


def _maybe_env(name: str) -> str | None:
    value = os.getenv(name)
    return value if value else None


def resolve_provider() -> TauProvider:
    """Resolve the Tau provider and model from the platform's LLM env vars."""
    provider = (_maybe_env("LLM_PROVIDER") or "").strip().lower()
    if not provider:
        if _maybe_env("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif _maybe_env("DEEPSEEK_API_KEY"):
            provider = "deepseek"
        else:
            provider = "openai"

    if provider == "anthropic":
        return TauProvider(
            provider="anthropic",
            model=_maybe_env("LLM_MODEL") or "claude-sonnet-4-6",
            api_key_env="ANTHROPIC_API_KEY",
        )

    base_url = _maybe_env("LLM_BASE_URL")
    if provider == "deepseek":
        base_url = base_url or _maybe_env("DEEPSEEK_BASE_URL")
        model = _maybe_env("LLM_MODEL") or _maybe_env("DEEPSEEK_MODEL") or "deepseek-chat"
        api_key_env = "LLM_API_KEY" if _maybe_env("LLM_API_KEY") else "DEEPSEEK_API_KEY"
    else:
        model = _maybe_env("LLM_MODEL") or "gpt-4o-mini"
        api_key_env = "LLM_API_KEY" if _maybe_env("LLM_API_KEY") else "OPENAI_API_KEY"

    # A base URL matching the provider's own endpoint is not custom: the built-in
    # catalog entry already points there.
    if base_url and base_url.rstrip("/") == _DEFAULT_BASE_URLS.get(provider, "").rstrip("/"):
        base_url = None

    if base_url is None:
        return TauProvider(provider=provider, model=model, api_key_env=api_key_env)

    return TauProvider(
        provider=CUSTOM_PROVIDER_NAME,
        model=model,
        api_key_env=api_key_env,
        base_url=base_url,
    )


def write_catalog_entry(target: TauProvider) -> None:
    """Register `target` as an OpenAI-compatible provider in the user catalog."""
    from tau_coding import (
        OpenAICompatibleProviderConfig,
        load_provider_settings,
        save_provider_settings,
        upsert_openai_compatible_provider,
    )

    if target.base_url is None:
        raise ValueError("write_catalog_entry requires a custom base_url")

    settings = load_provider_settings()
    provider = OpenAICompatibleProviderConfig(
        name=target.provider,
        base_url=target.base_url.rstrip("/"),
        api_key_env=target.api_key_env,
        models=(target.model,),
        default_model=target.model,
        thinking_levels=("off", "minimal", "low", "medium", "high", "xhigh"),
        thinking_parameter="reasoning_effort",
    )
    updated = upsert_openai_compatible_provider(settings, provider, set_default=True)
    save_provider_settings(updated)


def ensure_catalog_entry(target: TauProvider | None = None) -> None:
    """Ensure Tau catalog has an entry registered for custom gateway / base_url."""
    if target is None:
        target = resolve_provider()
    if target.needs_catalog_entry:
        write_catalog_entry(target)


def main() -> int:
    target = resolve_provider()
    if not target.needs_catalog_entry:
        print(
            f"[agent] tau provider '{target.provider}' is built in; "
            f"model={target.model} key={target.api_key_env}"
        )
        return 0

    write_catalog_entry(target)
    print(
        f"[agent] registered custom tau provider '{target.provider}' "
        f"base_url={target.base_url} model={target.model} key={target.api_key_env}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
