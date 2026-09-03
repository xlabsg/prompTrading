// API Types matching backend schemas

export type ChatStatus = "chatting" | "ready" | "generating" | "done";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type JobType =
    | "backtest"
    | "generate_strategy"
    | "refine_strategy"
    | "generate_and_backtest"
    | "repo_import"
    | "repo_sync";
export type BacktestStatus = "queued" | "running" | "succeeded" | "failed";
export type StrategyRole = "admin" | "editor" | "viewer";

export interface User {
    id: string;
    email?: string;
    name?: string;
    avatar_url?: string;
    created_at: string;
    last_login_at?: string;
}

export interface StrategyMember {
    id: string;
    strategy_id: string;
    role: StrategyRole;
    user: User;
    created_at: string;
}

export interface ExchangeAccountResponse {
    id: string;
    strategy_id: string;
    name: string;
    exchange: string;
    is_connected: boolean;
    created_at: string;
    updated_at: string;
}

export interface SignalResponse {
    id: string;
    strategy_id: string;
    session_id: string;
    symbol: string;
    interval?: string;
    side: string;
    price: number;
    confidence: number;
    target?: number;
    status: "pending" | "executed" | "cancelled" | "expired";
    reason?: string;
    params_snapshot?: Record<string, unknown>;
    indicators?: Record<string, unknown>;
    position?: Record<string, unknown>;
    price_source?: string;
    created_at: string;
}

export interface TradeResponse {
    id: string;
    session_id: string;
    symbol: string;
    side: string;
    entry_price: number;
    exit_price?: number;
    quantity: number;
    pnl?: number;
    fee: number;
    status: "open" | "closed" | "partial";
    created_at: string;
    closed_at?: string;
}

export interface CheckoutSessionResponse {
    url: string;
}

export interface SubscriptionStatusResponse {
    is_active: boolean;
    status?: string;
    plan_id?: string;
    current_period_end?: string;
    free_strategy_limit: number;
    strategies_used: number;
}

export interface OAuthStartResponse {
    auth_url: string;
}

export interface Strategy {
    id: string;
    name: string;
    created_at: string;
    updated_at: string;
    repo_id?: string;
    chat_status: ChatStatus;
    chat_history?: ChatMessage[];
    chat_config?: Record<string, unknown>;
}

export interface StrategyGitCompareFile {
    path: string;
    status: "A" | "M" | "D" | string;
    additions: number;
    deletions: number;
}

export interface StrategyGitCompareResponse {
    head_commit: string | null;
    base_commit: string | null;
    subject: string;
    files: StrategyGitCompareFile[];
}

export interface StrategyGitCompareDiffResponse {
    path: string;
    diff: string;
}

export interface StrategyVersion {
    id: string;
    strategy_id: string;
    version: number;
    created_at: string;
    workspace_path: string;
    prompt?: string;
    llm_meta?: Record<string, unknown>;
}

export interface ChatMessage {
    role: "user" | "assistant";
    content: string;
    summary?: string;
}

export type ChangeOperationType =
    | "exact_replace"
    | "range_replace"
    | "insert_after"
    | "insert_before"
    | "unified_diff";

export interface ChangeOperation {
    type: ChangeOperationType;
    old_text?: string;
    new_text?: string;
    start_line?: number;
    end_line?: number;
    replacement?: string;
    anchor?: string;
    insert_text?: string;
    diff_content?: string;
    description?: string;
    file_path?: string;
}

export interface ChangeSpec {
    operations: ChangeOperation[];
    version?: number;
}

export interface ChangeOperationResult {
    operation_index: number;
    success: boolean;
    error_message?: string;
    lines_changed?: [number, number];
    diff_preview?: string;
}

export interface PatchReport {
    success: boolean;
    operations_applied: number;
    operations_failed: number;
    results: ChangeOperationResult[];
    final_diff?: string;
    error_summary?: string;
}

export interface RefineProposal {
    instructions: string;
    patch?: string;
    change_spec?: ChangeSpec;
    source_message?: string;
}

export interface ChatResponse {
    reply: string;
    status: ChatStatus;
    chat_history: ChatMessage[];
    config?: Record<string, unknown>;
    refine_proposal?: RefineProposal | null;
}

export interface Dataset {
    id: string;
    exchange: string;
    symbol: string;
    interval: string;
    start_ms?: number;
    end_ms?: number;
    created_at: string;
}

export interface DatasetRequest {
    exchange: string;
    symbol: string;
    interval: string;
    start_ms?: number;
    end_ms?: number;
}

export interface USStockSymbol {
    symbol: string;
    name: string;
    sector: string;
    exchange: string;
    session: string;
}

export interface BacktestRun {
    id: string;
    strategy_id: string;
    strategy_version_id?: string;
    dataset_id?: string;
    job_id?: string;
    status: BacktestStatus;
    created_at: string;
    started_at?: string;
    finished_at?: string;
    run_path: string;
    params: Record<string, unknown>;
    metrics?: BacktestMetrics;
    error_message?: string;
}

export interface BacktestMetrics {
    total_return?: number;
    benchmark_return?: number;
    alpha?: number;
    sharpe_ratio?: number;
    max_drawdown?: number;
    win_rate?: number;
    total_trades?: number;
    profit_factor?: number;
    [key: string]: unknown;
}

export interface BacktestTrade {
    side: "long" | "short" | string;
    entry_time: string;
    exit_time: string;
    entry_time_ms?: number;
    exit_time_ms?: number;
    entry_price: number;
    exit_price: number;
    return_pct: number;
    pnl: number;
    duration: string;
    holding_time_ms?: number;
}

export interface BacktestOrder {
    time: string;
    time_ms: number;
    side: "buy" | "sell" | string;
    position_side?: "long" | "short" | "flat" | string;
    signal_source?: "entries_exits" | "target_weights" | "unknown" | string;
    signal_type?: "entry" | "exit" | "rebalance" | "flip" | "noop" | string;
    signal_reason?: string;
    signal_detail?: string;
    decision_id?: string | null;
    protocol_version?: string | null;
    signal_symbol?: string | null;
    decision_ts?: number | null;
    expires_at?: number | null;
    qty: number;
    price: number;
    notional: number;
    fee: number;
    weight_from: number;
    weight_to: number;
    units_before?: number;
    units_after?: number;
    equity_before?: number;
    equity_after?: number;
    entries_raw?: boolean | null;
    exits_raw?: boolean | null;
    target_weight?: number | string | boolean | null;
    features?: Record<string, unknown> | null;
}

export interface BacktestPosition {
    side: "long" | "short" | string;
    entry_time: string;
    exit_time: string;
    entry_time_ms?: number;
    exit_time_ms?: number;
    signal_source?: "entries_exits" | "target_weights" | "unknown" | string;
    entry_price: number;
    exit_price: number;
    entry_qty: number;
    max_qty: number;
    avg_qty?: number;
    scale_in_qty?: number;
    rebalance_count?: number;
    pnl: number;
    return_pct: number;
    duration_bars?: number;
    holding_time_ms?: number;
}

export interface BacktestSignalEvent {
    i: number;
    time: string;
    time_ms: number;
    type: "entry" | "exit" | "rebalance" | "flip" | string;
    side: "long" | "short" | string;
    signal_source?: "entries_exits" | "target_weights" | "unknown" | string;
    signal_reason?: string;
    signal_detail?: string;
    decision_id?: string | null;
    protocol_version?: string | null;
    signal_symbol?: string | null;
    decision_ts?: number | null;
    expires_at?: number | null;
    price: number;
    weight_from: number;
    weight_to: number;
    entries_raw?: boolean | null;
    exits_raw?: boolean | null;
    target_weight?: number | string | boolean | null;
    features?: Record<string, unknown> | null;
}

export interface BacktestSignalsPayload {
    schema: string;
    n: number;
    series: Record<string, unknown[]>;
    meta?: Record<string, unknown>;
}

export interface BacktestCandle {
    timestamp: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
    vol?: number;
}

export interface Job {
    id: string;
    type: JobType;
    status: JobStatus;
    created_at: string;
    started_at?: string;
    finished_at?: string;
    payload: Record<string, unknown>;
    error_message?: string;
}

export interface TriggerJobResponse {
    job: Job;
    backtest_run?: BacktestRun;
    strategy_version?: StrategyVersion;
    strategy?: Strategy;  // For repo import - the created/linked strategy
}

export interface Repo {
    id: string;
    provider: string;
    owner: string;
    name: string;
    default_branch?: string;
    tracked_branches?: string[];
    status: string;
    quota_state: string;
    size_bytes: number;
    last_error?: string;
    created_at: string;
    updated_at: string;
}

export interface RepoImportRequest {
    owner: string;
    name: string;
    branches?: string[];
    installation_id?: string;
}

export interface RepoTreeEntry {
    path: string;
    type: "file";
    size?: number;
}

export interface RepoTreeResponse {
    branch: string;
    entries: RepoTreeEntry[];
    truncated: boolean;
}

export interface RepoFileResponse {
    path: string;
    branch: string;
    content: string;
}

export interface SearchHit {
    repo_id: string;
    branch: string;
    path: string;
    lang?: string;
    snippet?: string;
    score?: number;
}

export interface SearchResponse {
    total: number;
    hits: SearchHit[];
}

export interface GitHubInstallation {
    id: number;
    account?: {
        login?: string;
        type?: string;
    };
}

export interface GitHubRepo {
    id: number;
    name: string;
    full_name?: string;
    private?: boolean;
    default_branch?: string;
    owner?: {
        login?: string;
    };
}

// Request types
export interface BacktestCreateRequest {
    dataset: DatasetRequest;
    params?: Record<string, unknown>;
}

export interface GenerateStrategyRequest {
    prompt: string;
    llm_meta?: Record<string, unknown>;
}

export interface GenerateAndBacktestRequest {
    prompt: string;
    dataset?: {
        exchange?: string;
        symbol?: string;
        interval?: string;
        start_ms?: number;
        end_ms?: number;
    };
    params?: Record<string, unknown>;
    llm_meta?: Record<string, unknown>;
}

export interface RefineStrategyRequest {
    prompt: string;
    patch?: string;
    change_spec?: ChangeSpec;
    llm_meta?: Record<string, unknown>;
}

// ============== Trading Types ==============

export type TradingSessionStatus = "starting" | "running" | "stopping" | "stopped" | "error";
export type OrderSide = "buy" | "sell";
export type OrderType = "market" | "limit";
export type OrderStatus = "pending" | "open" | "filled" | "partially_filled" | "cancelled" | "failed";
export type PositionSide = "long" | "short";
export type PositionStatus = "open" | "closed";

export interface TradingConfig {
    id: string;
    strategy_id: string;
    exchange: string;
    symbol: string;
    symbols?: string[];
    intervals?: string[];
    max_position_pct: number;
    stop_loss_pct: number;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface TradingConfigCreate {
    exchange: string;
    symbol?: string;
    symbols?: string[];
    intervals?: string[];
    api_key: string;
    api_secret: string;
    api_passphrase?: string;
    max_position_pct?: number;
    stop_loss_pct?: number;
}

export interface TradingSession {
    id: string;
    config_id: string;
    status: TradingSessionStatus;
    started_at: string;
    stopped_at?: string;
    total_pnl: number;
    total_trades: number;
    error_message?: string;
}

export interface TradingStatus {
    config?: TradingConfig;
    active_session?: TradingSession;
    is_trading: boolean;
}

export interface TradingOrder {
    id: string;
    session_id: string;
    exchange_order_id?: string;
    symbol: string;
    side: OrderSide;
    order_type: OrderType;
    price?: number;
    size: number;
    filled_size: number;
    avg_fill_price?: number;
    status: OrderStatus;
    created_at: string;
}

export interface TradingPosition {
    id: string;
    session_id: string;
    symbol: string;
    side: PositionSide;
    size: number;
    entry_price: number;
    current_price: number;
    unrealized_pnl: number;
    realized_pnl: number;
    status: PositionStatus;
    opened_at: string;
    closed_at?: string;
}

// ============== Trending Strategies Types ==============

export type TrendingSourceType = "idea" | "script";
export type TrendingBacktestStatus = "pending" | "running" | "completed" | "failed";

export interface BacktestSummary {
    total_return: number;
    max_drawdown: number;
    sharpe_ratio: number;
    win_rate: number;
    profit_factor?: number;
    run_id: string;
}

export interface TrendingStrategy {
    id: string;
    source_type: TrendingSourceType;
    tradingview_id: string;
    title: string;
    description: string | null;
    author: string | null;
    author_url: string | null;
    likes: number;
    views: number;
    comments: number;
    detected_symbols: string[];
    detected_markets: string[];
    scraped_at: string;
    trending_rank?: number;
    trending_category?: string;
    backtest_status: TrendingBacktestStatus;
    backtest_results?: Record<string, BacktestSummary>;
    backtest_error?: string | null;
    url: string;
    image_url?: string | null;
}

export interface TrendingListResponse {
    total: number;
    strategies: TrendingStrategy[];
}

export interface TrendingScrapeRequest {
    source_types: TrendingSourceType[];
    max_count?: number;
    auto_backtest?: boolean;
    auto_backtest_top_n?: number;
}

export interface TrendingScrapeResponse {
    job_id: string;
    message: string;
}

// ============== Strategy Template Types ==============

export type TemplateType = "builtin" | "tradingview" | "community";
export type SubscriptionStatusType = "active" | "paused" | "sync_error" | "outdated";

export interface TemplateListItem {
    id: string;
    name: string;
    description: string | null;
    template_type: TemplateType;
    author: string | null;
    tags: string[] | null;
    subscriber_count: number;
    is_featured: boolean;
    stable5_qualifies?: boolean | null;
    stable5_score?: number | null;
    created_at: string;
}

export interface TemplateDetail {
    id: string;
    name: string;
    description: string | null;
    template_type: TemplateType;
    author: string | null;
    tags: string[] | null;
    config_snapshot: Record<string, unknown> | null;
    prompt: string | null;
    version: number;
    is_featured: boolean;
    subscriber_count: number;
    created_at: string;
    updated_at: string;
}

export interface TemplateListResponse {
    total: number;
    templates: TemplateListItem[];
}

export interface Stable5RecommendationItem {
    id: string;
    name: string;
    description: string | null;
    template_type: TemplateType | string;
    author: string | null;
    tags: string[] | null;
    subscriber_count: number;
    is_featured: boolean;
    stable5: Record<string, unknown>;
}

export interface RunStable5ScreeningRequest {
    limit?: number;
    template_ids?: string[];
}

export interface RunStable5ScreeningResponse {
    message: string;
    job_id: string;
}

export interface SubscribeRequest {
    name: string;
    exchange: string;
    symbols: string[];
    api_key_encrypted: string;
    api_secret_encrypted: string;
    api_passphrase_encrypted?: string;
    max_position_pct: number;
    stop_loss_pct: number;
    custom_params?: Record<string, unknown>;
    telegram_config?: TelegramConfigRequest;
}

export interface SubscribeResponse {
    subscription_id: string;
    strategy_id: string;
    strategy_name: string;
    message: string;
}

export interface ForkTemplateRequest {
    name: string;
    description?: string;
}

export interface ForkTemplateResponse {
    strategy_id: string;
    strategy_name: string;
    version_id: string;
    message: string;
}

// ============== Template Performance Types ==============

export interface PerformanceMetrics {
    total_return: number;
    sharpe_ratio: number;
    max_drawdown: number;
    win_rate: number;
    total_trades: number;
    profit_factor: number;
    avg_trade_pnl: number;
}

export interface BacktestRunListItem {
    id: string;
    run_date: string;
    exchange: string;
    symbol: string;
    total_return: number;
    sharpe_ratio: number;
    max_drawdown: number;
    win_rate: number;
}

export interface TemplateSignalResponse {
    id: string;
    symbol: string;
    side: string;
    price: number;
    confidence: number;
    status: string;
    entry_price?: number;
    exit_price?: number;
    pnl?: number;
    hold_duration_hours?: number;
    created_at: string;
    executed_at?: string;
}

export interface TemplatePerformanceResponse {
    template_id: string;
    aggregated_metrics: PerformanceMetrics;
    backtest_runs: BacktestRunListItem[];
    recent_signals: TemplateSignalResponse[];
    total_signals: number;
}

export interface TemplatePerformanceRunDetailResponse {
    id: string;
    template_id: string;
    run_date: string;
    exchange: string;
    symbol: string;
    interval: string;
    start_ms?: number | null;
    end_ms?: number | null;
    metrics: Record<string, unknown>;
}

export interface PerformanceChartResponse {
    equity_curve: [number, number][];
    returns_distribution: { range: string; count: number }[];
    win_rate_trend: [string, number][];
}


export interface SubscriptionResponse {
    id: string;
    template_id: string;
    template_name: string;
    strategy_id: string;
    strategy_name: string;
    status: SubscriptionStatusType;
    subscribed_version: number;
    template_version: number;
    is_outdated: boolean;
    last_synced_at: string | null;
    user_config: Record<string, unknown> | null;
    telegram_config: Record<string, unknown> | null;
    telegram_status: TelegramStatus | null;
    created_at: string;
}

export interface SubscriptionListResponse {
    total: number;
    subscriptions: SubscriptionResponse[];
}

export interface SyncResultResponse {
    subscription_id: string;
    strategy_id: string;
    previous_version: number;
    new_version: number;
    message: string;
}

export interface UserConfigUpdateRequest {
    exchange?: string | null;
    symbol?: string | null;
    max_position_pct?: number | null;
    stop_loss_pct?: number | null;
    custom_params?: Record<string, unknown> | null;
}

// ============== Telegram Types ==============

export interface TelegramConfigRequest {
    bot_token_encrypted: string;
    chat_id: string;
    enabled?: boolean;
    notify_on_signal?: boolean;
    notify_on_execution?: boolean;
    notify_on_error?: boolean;
}

export interface TelegramTestResponse {
    success: boolean;
    message: string;
    bot_username?: string;
}

export interface TelegramStatus {
    is_configured: boolean;
    is_enabled: boolean;
    last_notification_at: string | null;
    error: string | null;
}

export interface TelegramConfigUpdateRequest {
    bot_token_encrypted?: string | null;
    chat_id?: string | null;
    enabled?: boolean | null;
    notify_on_signal?: boolean | null;
    notify_on_execution?: boolean | null;
    notify_on_error?: boolean | null;
}
