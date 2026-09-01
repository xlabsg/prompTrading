from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    db_url: str
    redis_url: str
    workspaces_dir: str = "/workspaces"
    public_base_url: str = "http://localhost:3000"
    sandbox_base_url: str = "http://localhost:8080"
    worker_rpc_base_url: str = "http://worker-rpc:8010"
    worker_rpc_token: Optional[str] = None
    worker_rpc_timeout_s: float = 10.0
    okx_simulated_trading: bool = False
    log_dir: str = "/var/log/app"

    # Repositories and search index locations (shared volume)
    repos_dir: Optional[str] = None  # default: f"{workspaces_dir}/repos"
    search_index_path: Optional[str] = None  # default: f"{workspaces_dir}/search/search.sqlite"

    # GitHub App configuration (optional during local dev)
    github_app_id: Optional[str] = None
    github_app_private_key: Optional[str] = None  # PEM content or path (future)
    github_app_webhook_secret: Optional[str] = None
    github_app_slug: Optional[str] = None  # App slug for installation URL

    # OAuth configuration (Google/GitHub)
    google_oauth_client_id: Optional[str] = None
    google_oauth_client_secret: Optional[str] = None
    google_oauth_redirect_uri: Optional[str] = None
    github_oauth_client_id: Optional[str] = None
    github_oauth_client_secret: Optional[str] = None
    github_oauth_redirect_uri: Optional[str] = None
    auth_session_days: int = 14

    # Stripe billing
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_price_id: str = "price_default"
    free_strategy_limit: int = 3

    # Development settings
    dev_skip_subscription_check: bool = True  # Default to True for easy development

    # Trending (TradingView) scraping
    trending_scrape_enabled: bool = False

    # Refine patch validation wait (seconds)
    refine_wait_timeout_s: int = 300

    # Admin access control (temporary): allowlist by email or a static API key.
    # APP_ADMIN_EMAILS supports comma/space-separated emails or a JSON list string.
    # Keep this as str to avoid pydantic-settings JSON parsing errors for list types.
    admin_emails: str = ""
    admin_api_key: Optional[str] = None


settings = Settings()
