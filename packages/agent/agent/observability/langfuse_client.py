"""
Langfuse client wrapper for observability.

Design principles:
- Optional feature (can be disabled via env)
- Single instance for the entire application
- Non-blocking (async flush)
- Graceful degradation if unavailable
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LangfuseConfig:
    """Configuration for Langfuse client.

    Attributes:
        enabled: Whether Langfuse tracing is enabled.
        public_key: Langfuse public key.
        secret_key: Langfuse secret key.
        host: Custom Langfuse host URL (for self-hosted instances).
        base_url: Langfuse base URL (alias for host, used by SDK).
        tracing_environment: Environment name for traces.
        session_id: Session identifier for trace grouping.
        user_id: User identifier for attribution.
    """

    enabled: bool = True
    public_key: Optional[str] = None
    secret_key: Optional[str] = None
    host: Optional[str] = None
    base_url: Optional[str] = None
    tracing_environment: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None

    @classmethod
    def from_env(cls) -> LangfuseConfig:
        """Create configuration from environment variables.

        Environment variables:
            LANGFUSE_PUBLIC_KEY: Langfuse public key
            LANGFUSE_SECRET_KEY: Langfuse secret key
            LANGFUSE_HOST: Custom host URL (optional)
            LANGFUSE_BASE_URL: Langfuse base URL (optional, overrides host)
            LANGFUSE_TRACING_ENVIRONMENT: Environment name (e.g., "dev", "prod")
            LANGFUSE_SESSION_ID: Session identifier (optional)
            LANGFUSE_USER_ID: User identifier (optional)
            STRATEGY_ID: Used as session_id fallback (optional)
            USER_ID: User identifier fallback (optional)

        Returns:
            A LangfuseConfig instance.
        """
        # LANGFUSE_BASE_URL takes precedence over LANGFUSE_HOST
        base_url = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST")

        return cls(
            enabled=True,  # Enabled when credentials are provided
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=base_url,
            base_url=base_url,
            tracing_environment=os.getenv("LANGFUSE_TRACING_ENVIRONMENT"),
            session_id=os.getenv("LANGFUSE_SESSION_ID") or os.getenv("STRATEGY_ID"),
            user_id=os.getenv("LANGFUSE_USER_ID") or os.getenv("USER_ID"),
        )


class LangfuseClient:
    """Langfuse client singleton.

    Wraps the official Langfuse client with:
    - Lazy initialization
    - Optional/disableable support
    - Graceful error handling
    """

    _instance: Optional[LangfuseClient] = None
    _client: Any = None  # langfuse.Langfuse (lazy import)
    _config: LangfuseConfig = LangfuseConfig()

    def __new__(cls) -> LangfuseClient:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Only initialize once
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        config = LangfuseConfig.from_env()
        self._config = config

        # Check for required credentials
        if not config.public_key or not config.secret_key:
            self._client = None
            return

        try:
            from langfuse import Langfuse as _Langfuse

            # Initialize with base_url (SDK uses "host" parameter)
            self._client = _Langfuse(
                public_key=config.public_key,
                secret_key=config.secret_key,
                host=config.base_url,  # SDK calls it "host" but it's the base URL
                session_id=config.session_id,
                user_id=config.user_id,
                traces_sample_rate=1.0,  # Sample rate for traces
            )
        except Exception:
            # Langfuse not available or import failed
            self._client = None

    @property
    def enabled(self) -> bool:
        """Check if Langfuse tracing is enabled and available.

        Returns:
            True if tracing is enabled and client is initialized.
        """
        return self._client is not None

    @property
    def config(self) -> LangfuseConfig:
        """Get the current configuration.

        Returns:
            The LangfuseConfig instance.
        """
        return self._config

    def create_trace(
        self,
        name: str,
        metadata: dict[str, Any],
    ) -> Any:
        """Create a new trace.

        Args:
            name: Trace name.
            metadata: Trace metadata.

        Returns:
            Langfuse StatefulTrace object, or None if disabled.
        """
        if not self.enabled:
            return None

        return self._client.create_trace(  # type: ignore[union-attr]
            name=name,
            session_id=self._config.session_id,
            user_id=self._config.user_id,
            metadata=metadata,
        )

    def flush(self) -> None:
        """Flush pending events to Langfuse.

        Should be called before application exit to ensure
        all data is sent.
        """
        if self.enabled and self._client:
            # Use async flush to avoid blocking
            self._client.flush_async()  # type: ignore[union-attr]


# Global singleton accessor
_global_client: LangfuseClient | None = None


def get_langfuse() -> LangfuseClient:
    """Get the global Langfuse client singleton.

    Returns:
        The global LangfuseClient instance.
    """
    global _global_client
    if _global_client is None:
        _global_client = LangfuseClient()
    return _global_client


__all__ = ["LangfuseClient", "LangfuseConfig", "get_langfuse"]
