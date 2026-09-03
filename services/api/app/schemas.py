from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from control_plane.enums import (
    BacktestStatus,
    ChatStatus,
    JobStatus,
    JobType,
    StrategyRole,
    SignalStatus,
    TradeStatus,
)


class StrategyCreateRequest(BaseModel):
    name: Optional[str] = None


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    repo_id: Optional[str] = None
    chat_status: ChatStatus
    chat_history: Optional[list[dict[str, Any]]] = None
    chat_config: Optional[dict[str, Any]] = None


class StrategyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    version: int
    created_at: datetime
    workspace_path: str
    prompt: Optional[str] = None
    llm_meta: Optional[dict[str, Any]] = None


class DatasetRequest(BaseModel):
    exchange: str = Field(default="binance")
    symbol: str = Field(default="BTCUSDT")
    interval: str = Field(default="1h")
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exchange: str
    symbol: str
    interval: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    created_at: datetime


class USStockSymbolResponse(BaseModel):
    symbol: str
    name: str
    sector: str
    exchange: str
    session: str


class BacktestCreateRequest(BaseModel):
    dataset: DatasetRequest = Field(default_factory=DatasetRequest)
    params: dict[str, Any] = Field(default_factory=dict)


class GenerateAndBacktestRequest(BaseModel):
    prompt: str
    dataset: DatasetRequest = Field(default_factory=DatasetRequest)
    params: dict[str, Any] = Field(default_factory=dict)
    llm_meta: dict[str, Any] = Field(default_factory=dict)


class GenerateStrategyRequest(BaseModel):
    prompt: str
    llm_meta: dict[str, Any] = Field(default_factory=dict)


class LiveGenerateRequest(BaseModel):
    prompt: str


class LiveGenerateResponse(BaseModel):
    summary: str
    code: str


class LiveConfirmRequest(BaseModel):
    code: str
    summary: Optional[str] = None


class ChangeOperationType(str, Enum):
    """Types of change operations supported by PatchEngine."""
    EXACT_REPLACE = "exact_replace"
    RANGE_REPLACE = "range_replace"
    INSERT_AFTER = "insert_after"
    INSERT_BEFORE = "insert_before"
    UNIFIED_DIFF = "unified_diff"


class ChangeOperation(BaseModel):
    """
    A single change operation to apply to a file.

    Different operation types require different fields:
    - exact_replace: old_text, new_text
    - range_replace: start_line, end_line, replacement
    - insert_after/insert_before: anchor, insert_text
    - unified_diff: diff_content
    """
    type: ChangeOperationType

    # For exact_replace
    old_text: Optional[str] = None
    new_text: Optional[str] = None

    # For range_replace
    start_line: Optional[int] = None  # 1-indexed
    end_line: Optional[int] = None    # inclusive
    replacement: Optional[str] = None

    # For insert_after/insert_before
    anchor: Optional[str] = None
    insert_text: Optional[str] = None

    # For unified_diff
    diff_content: Optional[str] = None

    # Optional metadata
    description: Optional[str] = None
    file_path: str = "strategy.py"


class ChangeSpec(BaseModel):
    """Collection of change operations to apply."""
    operations: list[ChangeOperation]
    version: int = 1


class ChangeOperationResult(BaseModel):
    """Result of applying a single change operation."""
    operation_index: int
    success: bool
    error_message: Optional[str] = None
    lines_changed: Optional[tuple[int, int]] = None
    diff_preview: Optional[str] = None


class PatchReport(BaseModel):
    """Complete report of patch application."""
    success: bool
    operations_applied: int
    operations_failed: int
    results: list[ChangeOperationResult]
    final_diff: Optional[str] = None
    error_summary: Optional[str] = None


class RefineStrategyRequest(BaseModel):
    prompt: str
    patch: Optional[str] = None  # Legacy unified diff
    change_spec: Optional[ChangeSpec] = None  # New structured format
    llm_meta: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    summary: Optional[str] = None


class ChatRequest(BaseModel):
    message: str


class RefineProposal(BaseModel):
    instructions: str
    patch: Optional[str] = None  # Legacy unified diff
    change_spec: Optional[ChangeSpec] = None  # New structured format
    source_message: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    status: ChatStatus
    chat_history: list[dict[str, Any]]
    config: Optional[dict[str, Any]] = None  # When status is "ready", contains the final config
    refine_proposal: Optional[RefineProposal] = None


class BacktestRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    strategy_version_id: Optional[str] = None
    dataset_id: Optional[str] = None
    job_id: Optional[str] = None
    status: BacktestStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    run_path: str
    params: dict[str, Any]
    metrics: Optional[dict[str, Any]] = None
    result_summary: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: JobType
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    payload: dict[str, Any]
    error_message: Optional[str] = None


class TriggerJobResponse(BaseModel):
    job: JobResponse
    backtest_run: Optional[BacktestRunResponse] = None
    strategy_version: Optional[StrategyVersionResponse] = None
    strategy: Optional[StrategyResponse] = None  # For repo import - the created/linked strategy


# --- Repositories & search ---

class RepoImportRequest(BaseModel):
    owner: str
    name: str
    branches: Optional[list[str]] = None  # None -> use default only
    installation_id: Optional[str] = None  # optional for private repos (GitHub App install)


class RepoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    owner: str
    name: str
    default_branch: Optional[str] = None
    tracked_branches: Optional[list[str]] = None
    status: str
    quota_state: str
    size_bytes: int
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SearchQuery(BaseModel):
    q: str
    repo_id: Optional[str] = None
    branch: Optional[str] = None
    path_prefix: Optional[str] = None
    ext: Optional[str] = None
    limit: int = 20
    offset: int = 0


class SearchHit(BaseModel):
    repo_id: str
    branch: str
    path: str
    lang: Optional[str] = None
    snippet: Optional[str] = None
    score: Optional[float] = None


class SearchResponse(BaseModel):
    total: int
    hits: list[SearchHit]


# --- Auth & user management ---

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None


class AuthMeResponse(BaseModel):
    user: UserResponse
    is_admin: bool = False


class OAuthStartRequest(BaseModel):
    redirect_path: Optional[str] = None
    invite_code: Optional[str] = None


class OAuthStartResponse(BaseModel):
    auth_url: str


class StrategyMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    role: StrategyRole
    user: UserResponse
    created_at: datetime


class StrategyMemberCreateRequest(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    role: StrategyRole = StrategyRole.VIEWER


class ExchangeAccountCreateRequest(BaseModel):
    name: str
    exchange: str
    api_key: str
    api_secret: str
    api_passphrase: Optional[str] = None


class ExchangeAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    name: str
    exchange: str
    is_connected: bool
    created_at: datetime
    updated_at: datetime


class ExchangeAccountUpdateRequest(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    api_passphrase: Optional[str] = None
    is_connected: Optional[bool] = None


class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    session_id: str
    symbol: str
    interval: Optional[str] = None
    side: str
    price: float
    confidence: float
    target: Optional[float] = None
    status: SignalStatus
    reason: Optional[str] = None
    params_snapshot: Optional[dict[str, Any]] = None
    indicators: Optional[dict[str, Any]] = None
    position: Optional[dict[str, Any]] = None
    price_source: Optional[str] = None
    created_at: datetime


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float
    pnl: Optional[float] = None
    fee: float
    status: TradeStatus
    created_at: datetime
    closed_at: Optional[datetime] = None


class CheckoutSessionResponse(BaseModel):
    url: str


class SubscriptionStatusResponse(BaseModel):
    is_active: bool
    status: Optional[str] = None
    plan_id: Optional[str] = None
    current_period_end: Optional[datetime] = None
    free_strategy_limit: int
    strategies_used: int


# --- Strategy Import ---

class ImportTradingViewRequest(BaseModel):
    """Request to import strategy from TradingView PineScript."""
    url: str = Field(..., description="TradingView script URL")
    strategy_name: Optional[str] = Field(None, description="Custom strategy name")


class ImportYouTubeRequest(BaseModel):
    """Request to import strategy from YouTube video."""
    url: str = Field(..., description="YouTube video URL")
    strategy_name: Optional[str] = Field(None, description="Custom strategy name")
    max_duration_seconds: int = Field(default=1800, description="Max video duration (default 30 min)")


class ImportStrategyResponse(BaseModel):
    """Response for strategy import requests."""
    job: JobResponse
    strategy: StrategyResponse
    strategy_version: Optional[StrategyVersionResponse] = None
    source_metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata from import source")
