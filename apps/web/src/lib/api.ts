// API utilities for backend communication
import type {
    Strategy,
    StrategyVersion,
    BacktestRun,
    TriggerJobResponse,
    Job,
    ChatResponse,
    BacktestCreateRequest,
    BacktestOrder,
    BacktestPosition,
    BacktestTrade,
    GenerateStrategyRequest,
    GenerateAndBacktestRequest,
    RefineStrategyRequest,
    Repo,
    RepoImportRequest,
    RepoTreeResponse,
    RepoFileResponse,
    GitHubInstallation,
    GitHubRepo,
    User,
    StrategyMember,
    OAuthStartResponse,
    ExchangeAccountResponse,
    SignalResponse,
    TradeResponse,
    CheckoutSessionResponse,
    SubscriptionStatusResponse,
    USStockSymbol,
    TrendingListResponse,
    TrendingScrapeRequest,
    TrendingScrapeResponse,
    TrendingStrategy,
    TemplateListResponse,
    TemplateDetail,
    BacktestSignalsPayload,
    BacktestCandle,
    BacktestSignalEvent,
    SubscribeRequest,
    SubscribeResponse,
    ForkTemplateRequest,
    ForkTemplateResponse,
    SubscriptionListResponse,
    SubscriptionResponse,
    SyncResultResponse,
    UserConfigUpdateRequest,
    TelegramTestResponse,
    TelegramConfigUpdateRequest,
    JobStatus,
    TemplatePerformanceResponse,
    TemplatePerformanceRunDetailResponse,
    PerformanceChartResponse,
    StrategyGitCompareResponse,
    StrategyGitCompareDiffResponse,
} from "./types";

export function apiBaseUrl(): string {
    // Check for environment variable first
    if (import.meta.env.VITE_API_BASE_URL) {
        return import.meta.env.VITE_API_BASE_URL;
    }

    if (typeof window !== "undefined" && import.meta.env.PROD) {
        return window.location.origin;
    }

    // In docker-compose dev environment, we want to hit localhost:8000
    // even if PROD is false (Vite dev server)
    return "http://localhost:8000";
}

type ApiRequestOptions = RequestInit & {
    suppressAuthDialog?: boolean;
};

export async function fetchApi<T>(
    endpoint: string,
    options?: ApiRequestOptions
): Promise<T> {
    const baseUrl = apiBaseUrl();
    const { suppressAuthDialog, ...fetchOptions } = options ?? {};
    const response = await fetch(`${baseUrl}${endpoint}`, {
        credentials: "include",
        ...fetchOptions,
        headers: {
            "Content-Type": "application/json",
            ...fetchOptions.headers,
        },
    });

    if (!response.ok) {
        if (!suppressAuthDialog && response.status === 401 && typeof window !== "undefined") {
            window.dispatchEvent(new CustomEvent("auth-required"));
        }
        const error = await response.text();
        throw new Error(`API Error ${response.status}: ${error}`);
    }

    return response.json();
}

function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
    const parts = Object.entries(params)
        .filter(([, value]) => value !== undefined && value !== null && value !== "")
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
    return parts.length ? `?${parts.join("&")}` : "";
}

// ============== Strategies API ==============

export const strategiesApi = {
    list: () => fetchApi<Strategy[]>("/api/strategies"),

    get: (id: string) => fetchApi<Strategy>(`/api/strategies/${id}`),

    create: (name?: string) =>
        fetchApi<Strategy>("/api/strategies", {
            method: "POST",
            body: JSON.stringify({ name }),
        }),

    chat: (strategyId: string, message: string) =>
        fetchApi<ChatResponse>(`/api/strategies/${strategyId}/chat`, {
            method: "POST",
            body: JSON.stringify({ message }),
        }),

    chatStream: (strategyId: string, message: string) => {
        const baseUrl = apiBaseUrl();
        return fetch(`${baseUrl}/api/strategies/${strategyId}/chat/stream`, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message }),
        });
    },

    confirmChat: (strategyId: string) =>
        fetchApi<Strategy>(`/api/strategies/${strategyId}/chat/confirm`, {
            method: "POST",
        }),

    generate: (strategyId: string, req: GenerateStrategyRequest) =>
        fetchApi<TriggerJobResponse>(`/api/strategies/${strategyId}/generate`, {
            method: "POST",
            body: JSON.stringify(req),
        }),

    generateAndBacktest: (strategyId: string, req: GenerateAndBacktestRequest) =>
        fetchApi<TriggerJobResponse>(`/api/strategies/${strategyId}/generate_and_backtest`, {
            method: "POST",
            body: JSON.stringify(req),
        }),

    refine: (strategyId: string, req: RefineStrategyRequest) =>
        fetchApi<TriggerJobResponse>(`/api/strategies/${strategyId}/refine`, {
            method: "POST",
            body: JSON.stringify(req),
        }),

    listVersions: (strategyId: string) =>
        fetchApi<StrategyVersion[]>(`/api/strategies/${strategyId}/versions`),

    restoreVersion: (strategyId: string, versionId: string) =>
        fetchApi<Strategy>(`/api/strategies/${strategyId}/versions/${versionId}/restore`, {
            method: "POST",
        }),

    getFiles: (strategyId: string) =>
        fetchApi<{ files: Array<{ name: string; path: string; type: string; content: string }> }>(
            `/api/strategies/${strategyId}/files`
        ),

    getGitCompare: (strategyId: string) =>
        fetchApi<StrategyGitCompareResponse>(`/api/strategies/${strategyId}/git/compare`),

    getGitCompareDiff: (strategyId: string, path: string) =>
        fetchApi<StrategyGitCompareDiffResponse>(
            `/api/strategies/${strategyId}/git/compare/diff${buildQuery({ path })}`
        ),

    getWorkspaceCompare: (strategyId: string) =>
        fetchApi<StrategyGitCompareResponse>(`/api/strategies/${strategyId}/workspace/compare`),

    getWorkspaceCompareDiff: (strategyId: string, path: string) =>
        fetchApi<StrategyGitCompareDiffResponse>(
            `/api/strategies/${strategyId}/workspace/compare/diff${buildQuery({ path })}`
        ),

    checkLiveReady: (strategyId: string) =>
        fetchApi<{ is_live_ready: boolean; has_generate_signals: boolean; strategy_exists: boolean }>(
            `/api/strategies/${strategyId}/live-ready`
        ),
    generateLive: (strategyId: string, req: { prompt: string }) =>
        fetchApi<{ summary: string; code: string }>(
            `/api/strategies/${strategyId}/live/generate`,
            { method: "POST", body: JSON.stringify(req) }
        ),
    confirmLive: (strategyId: string, req: { code: string; summary?: string }) =>
        fetchApi<{ status: string; live_ready: boolean }>(
            `/api/strategies/${strategyId}/live/confirm`,
            { method: "POST", body: JSON.stringify(req) }
        ),
};

// ============== Backtests API ==============

export const backtestsApi = {
    create: (strategyId: string, req: BacktestCreateRequest) =>
        fetchApi<TriggerJobResponse>(`/api/strategies/${strategyId}/backtests`, {
            method: "POST",
            body: JSON.stringify(req),
        }),

    list: (strategyId: string) =>
        fetchApi<BacktestRun[]>(`/api/strategies/${strategyId}/backtests`),

    get: (runId: string) =>
        fetchApi<BacktestRun>(`/api/backtests/${runId}`),

    listArtifacts: (runId: string) =>
        fetchApi<string[]>(`/api/backtests/${runId}/artifacts`),

    getArtifactUrl: (runId: string, artifactName: string) =>
        `${apiBaseUrl()}/api/backtests/${runId}/artifacts/${artifactName}`,

    getEquityCurve: (runId: string) =>
        fetchApi<{ data: Array<{ timestamp: number; equity: number; drawdown: number; benchmark_equity?: number }> }>(`/api/backtests/${runId}/equity_curve`),

    getTrades: (runId: string) =>
        fetchApi<{ trades: BacktestTrade[] }>(`/api/backtests/${runId}/trades`),

    getOrders: (runId: string) =>
        fetchApi<{ orders: BacktestOrder[] }>(`/api/backtests/${runId}/orders`),

    getPositions: (runId: string) =>
        fetchApi<{ positions: BacktestPosition[] }>(`/api/backtests/${runId}/positions`),

    getSignals: (runId: string) =>
        fetchApi<BacktestSignalsPayload>(`/api/backtests/${runId}/signals`),

    getSignalEvents: (runId: string) =>
        fetchApi<{ events: BacktestSignalEvent[] }>(`/api/backtests/${runId}/signals/events`),

    getCandles: (runId: string) =>
        fetchApi<{ data: BacktestCandle[] }>(`/api/backtests/${runId}/candles`),

    getLog: async (runId: string): Promise<string> => {
        const baseUrl = apiBaseUrl();
        const res = await fetch(`${baseUrl}/api/backtests/${runId}/artifacts/backtest.log`, {
            credentials: "include",
        });
        if (!res.ok) return "";
        return res.text();
    },
};

export const templateBacktestsApi = {
    list: (templateId: string) =>
        fetchApi<BacktestRun[]>(`/api/templates/${templateId}/backtests`),

    get: (templateId: string, runId: string) =>
        fetchApi<BacktestRun>(`/api/templates/${templateId}/backtests/${runId}`),

    listArtifacts: (templateId: string, runId: string) =>
        fetchApi<string[]>(`/api/templates/${templateId}/backtests/${runId}/artifacts`),

    getArtifactUrl: (templateId: string, runId: string, artifactName: string) =>
        `${apiBaseUrl()}/api/templates/${templateId}/backtests/${runId}/artifacts/${artifactName}`,

    getEquityCurve: (templateId: string, runId: string) =>
        fetchApi<{ data: Array<{ timestamp: number; equity: number; drawdown: number; benchmark_equity?: number }> }>(
            `/api/templates/${templateId}/backtests/${runId}/equity_curve`,
        ),

    getTrades: (templateId: string, runId: string) =>
        fetchApi<{ trades: BacktestTrade[] }>(`/api/templates/${templateId}/backtests/${runId}/trades`),

    getOrders: (templateId: string, runId: string) =>
        fetchApi<{ orders: BacktestOrder[] }>(`/api/templates/${templateId}/backtests/${runId}/orders`),

    getPositions: (templateId: string, runId: string) =>
        fetchApi<{ positions: BacktestPosition[] }>(`/api/templates/${templateId}/backtests/${runId}/positions`),

    getSignals: (templateId: string, runId: string) =>
        fetchApi<BacktestSignalsPayload>(`/api/templates/${templateId}/backtests/${runId}/signals`),

    getSignalEvents: (templateId: string, runId: string) =>
        fetchApi<{ events: BacktestSignalEvent[] }>(`/api/templates/${templateId}/backtests/${runId}/signals/events`),

    getLog: async (templateId: string, runId: string): Promise<string> => {
        const baseUrl = apiBaseUrl();
        const res = await fetch(`${baseUrl}/api/templates/${templateId}/backtests/${runId}/artifacts/backtest.log`, {
            credentials: "include",
        });
        if (!res.ok) return "";
        return res.text();
    },
};

// ============== Jobs API ==============

export const jobsApi = {
    get: (jobId: string) => fetchApi<Job>(`/api/jobs/${jobId}`),

    // Poll job status until complete
    waitForCompletion: async (
        jobId: string,
        onProgress?: (job: Job) => void,
        interval = 2000,
        timeout = 420000
    ): Promise<Job> => {
        const startTime = Date.now();

        while (true) {
            const job = await jobsApi.get(jobId);
            onProgress?.(job);

            if (job.status === "succeeded" || job.status === "failed") {
                return job;
            }

            if (Date.now() - startTime > timeout) {
                throw new Error("Job timed out");
            }

            await new Promise((resolve) => setTimeout(resolve, interval));
        }
    },

    // Stream job events with fallback to polling
    waitForCompletionWithStream: async (
        jobId: string,
        onEvent?: (event: {
            type: string;
            step?: string;
            detail?: string;
            message?: string;
            line?: string;
            status?: string;
            tool?: string;
            path?: string;
            stage?: string;
        }) => void,
        timeout = 420000
    ): Promise<Job> => {
        const startTime = Date.now();
        return new Promise<Job>((resolve, reject) => {
            const timeoutTimer = setTimeout(() => {
                cleanup();
                jobsApi.get(jobId).then((job) => {
                    if (job.status === "succeeded" || job.status === "failed") {
                        resolve(job);
                    } else {
                        reject(new Error("Job timed out"));
                    }
                }).catch(reject);
            }, timeout);

            let eventSource: EventSource | null = null;
            let finished = false;

            const cleanup = () => {
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
                clearTimeout(timeoutTimer);
            };

            const complete = async () => {
                if (finished) return;
                finished = true;
                cleanup();
                try {
                    const elapsed = Date.now() - startTime;
                    const remainingTimeout = Math.max(timeout - elapsed, 10000);
                    const job = await jobsApi.waitForCompletion(jobId, undefined, 1000, remainingTimeout);
                    resolve(job);
                } catch (err) {
                    try {
                        const job = await jobsApi.get(jobId);
                        if (job.status === "succeeded" || job.status === "failed") {
                            resolve(job);
                            return;
                        }
                    } catch {
                        // ignore fetch failure, surface original error
                    }
                    reject(err);
                }
            };

            try {
                const streamUrl = `${apiBaseUrl()}/api/jobs/${jobId}/stream`;
                eventSource = new EventSource(streamUrl, { withCredentials: true });

                eventSource.addEventListener("step", (e) => {
                    try {
                        const data = JSON.parse(e.data);
                        onEvent?.({ type: "step", ...data });
                    } catch {
                        /* noop */
                    }
                });

                eventSource.addEventListener("progress", (e) => {
                    try {
                        const data = JSON.parse(e.data);
                        onEvent?.({ type: "progress", ...data });
                    } catch {
                        /* noop */
                    }
                });

                eventSource.addEventListener("log", (e) => {
                    try {
                        const data = JSON.parse(e.data);
                        onEvent?.({ type: "log", ...data });
                    } catch {
                        /* noop */
                    }
                });

                eventSource.addEventListener("finish", () => {
                    complete();
                });

                eventSource.onerror = () => {
                    // If stream errors out (e.g. proxy or premature close), complete via DB check/polling
                    complete();
                };
            } catch {
                jobsApi.waitForCompletion(jobId, undefined, 2000, timeout).then(resolve).catch(reject);
            }
        });
    },
};

// ============== Markets API ==============

export const marketsApi = {
    listUsStocks: (params: { q?: string; limit?: number; offset?: number; force_refresh?: boolean } = {}) =>
        fetchApi<USStockSymbol[]>(
            `/api/markets/us-stocks${buildQuery({
                q: params.q,
                limit: params.limit,
                offset: params.offset,
                force_refresh: params.force_refresh ? 1 : undefined,
            })}`
        ),
};

// ============== Repositories API ==============

export const reposApi = {
    list: () => fetchApi<Repo[]>("/api/repos"),
    get: (repoId: string) => fetchApi<Repo>(`/api/repos/${repoId}`),
    import: (req: RepoImportRequest) =>
        fetchApi<TriggerJobResponse>("/api/repos/import", {
            method: "POST",
            body: JSON.stringify(req),
        }),
    sync: (repoId: string) =>
        fetchApi<TriggerJobResponse>(`/api/repos/${repoId}/sync`, {
            method: "POST",
        }),
    tree: (repoId: string, params?: { branch?: string; max_entries?: number }) =>
        fetchApi<RepoTreeResponse>(`/api/repos/${repoId}/tree${buildQuery(params || {})}`),
    file: (repoId: string, params: { branch?: string; path: string; max_bytes?: number }) =>
        fetchApi<RepoFileResponse>(`/api/repos/${repoId}/file${buildQuery(params)}`),
};


// ============== GitHub API ==============

export const githubApi = {
    getInstallUrl: () => fetchApi<{ install_url: string; settings_url: string }>("/api/github/install-url"),
    listInstallations: () => fetchApi<GitHubInstallation[]>("/api/github/installations"),
    listInstallationRepos: (installationId: string) =>
        fetchApi<GitHubRepo[]>(`/api/github/installation/${installationId}/repos`),
};

// ============== Auth API ==============

export const authApi = {
    me: () => fetchApi<{ user: User; is_admin?: boolean }>("/api/auth/me", { suppressAuthDialog: true }),
    startOAuth: (provider: "google" | "github", redirect_path?: string) =>
        fetchApi<OAuthStartResponse>(`/api/auth/oauth/${provider}/start`, {
            method: "POST",
            body: JSON.stringify({ redirect_path }),
        }),
    logout: () =>
        fetchApi<{ ok: boolean }>("/api/auth/logout", {
            method: "POST",
        }),
};

// ============== Strategy Members API ==============

export const strategyMembersApi = {
    list: (strategyId: string) =>
        fetchApi<StrategyMember[]>(`/api/strategies/${strategyId}/members`),
    add: (strategyId: string, payload: { email?: string; user_id?: string; role?: string }) =>
        fetchApi<StrategyMember>(`/api/strategies/${strategyId}/members`, {
            method: "POST",
            body: JSON.stringify(payload),
        }),
    remove: (strategyId: string, memberId: string) =>
        fetchApi<{ ok: boolean }>(`/api/strategies/${strategyId}/members/${memberId}`, {
            method: "DELETE",
        }),
};

// ============== Exchange Accounts API ==============

export const exchangeAccountsApi = {
    list: (strategyId: string) =>
        fetchApi<ExchangeAccountResponse[]>(`/api/strategies/${strategyId}/exchange_accounts`),
    create: (strategyId: string, payload: { name: string; exchange: string; api_key: string; api_secret: string; api_passphrase?: string }) =>
        fetchApi<ExchangeAccountResponse>(`/api/strategies/${strategyId}/exchange_accounts`, {
            method: "POST",
            body: JSON.stringify(payload),
        }),
    update: (strategyId: string, accountId: string, payload: { name?: string; api_key?: string; api_secret?: string; api_passphrase?: string; is_connected?: boolean }) =>
        fetchApi<ExchangeAccountResponse>(`/api/strategies/${strategyId}/exchange_accounts/${accountId}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
        }),
    remove: (strategyId: string, accountId: string) =>
        fetchApi<{ ok: boolean }>(`/api/strategies/${strategyId}/exchange_accounts/${accountId}`, {
            method: "DELETE",
        }),
};

// ============== Signals & Trades API ==============

export const signalsApi = {
    list: (strategyId: string) =>
        fetchApi<SignalResponse[]>(`/api/strategies/${strategyId}/signals`),
};

export const tradesApi = {
    list: (strategyId: string) =>
        fetchApi<TradeResponse[]>(`/api/strategies/${strategyId}/trades`),
};

// ============== Billing API ==============

export const billingApi = {
    checkout: () =>
        fetchApi<CheckoutSessionResponse>(`/api/billing/checkout`, {
            method: "POST",
        }),
    status: () => fetchApi<SubscriptionStatusResponse>(`/api/billing/status`),
};

// ============== Portfolio API ==============

export interface PortfolioSummary {
    has_trading_config: boolean;
    has_active_session: boolean;
    balance?: {
        total_equity: number;
        available: number;
        frozen: number;
        unrealized_pnl: number;
        margin_used: number;
    };
    positions: PositionData[];
    total_pnl: number;
    total_trades: number;
}

export interface PositionData {
    inst_id: string;
    pos_side: string;
    pos: number;
    avg_px: number;
    mark_px: number;
    upl: number;
    upl_ratio: number;
    margin: number;
    lever: number;
    opened_at: string | null;
}

export interface OrderData {
    order_id: string;
    exchange_order_id?: string;
    symbol: string;
    inst_id: string;
    side: string;
    order_type: string;
    size: number;
    sz: number;
    px?: number;
    filled_size: number;
    avg_fill_price?: number;
    status: string;
    created_at: string;
}

export const portfolioApi = {
    listAccounts: (strategyId: string) =>
        fetchApi<ExchangeAccountResponse[]>(`/api/portfolio/${strategyId}/accounts`),

    getSummary: (strategyId: string, accountId?: string) =>
        fetchApi<PortfolioSummary>(`/api/portfolio/${strategyId}/summary${buildQuery({ account_id: accountId })}`),

    getPositions: (strategyId: string, accountId?: string) =>
        fetchApi<PositionData[]>(`/api/portfolio/${strategyId}/positions${buildQuery({ account_id: accountId })}`),

    getPendingOrders: (strategyId: string, accountId?: string) =>
        fetchApi<OrderData[]>(`/api/portfolio/${strategyId}/pending-orders${buildQuery({ account_id: accountId })}`),

    getOrderHistory: (strategyId: string, limit = 50, accountId?: string) =>
        fetchApi<{ items: OrderData[]; has_more: boolean }>(
            `/api/portfolio/${strategyId}/orders-history${buildQuery({ limit, account_id: accountId })}`
        ),

    getPositionsHistory: (strategyId: string, limit = 50, accountId?: string) =>
        fetchApi<PositionHistoryData[]>(`/api/portfolio/${strategyId}/positions-history${buildQuery({ limit, account_id: accountId })}`),

    getEquityCurve: (strategyId: string) =>
        fetchApi<EquityPoint[]>(`/api/portfolio/${strategyId}/equity-curve`),
};

// ============== Trading Logs API ==============

export interface LogEntry {
    id: string;
    session_id: string;
    level: "debug" | "info" | "warning" | "error";
    message: string;
    log_metadata?: Record<string, any>;
    created_at: string;
}

export interface PositionHistoryData {
    inst_id: string;
    pos_side: string;
    pos: number;
    entry_px: number;
    exit_px: number;
    realized_pnl: number;
    return_pct: number;
    opened_at: string;
    closed_at: string;
}

export interface EquityPoint {
    timestamp: string;
    equity: number;
}

export const tradingLogsApi = {
    list: (strategyId: string, params?: URLSearchParams) => {
        const query = params ? `?${params.toString()}` : "";
        return fetchApi<LogEntry[]>(`/api/strategies/${strategyId}/trading/logs${query}`);
    },
};

// ============== Trending Strategies API ==============

export const trendingApi = {
    scrape: (req: TrendingScrapeRequest) =>
        fetchApi<TrendingScrapeResponse>("/api/trending/scrape-now", {
            method: "POST",
            body: JSON.stringify(req),
        }),

    list: (params?: {
        source_type?: string;
        backtest_status?: string;
        sort_by?: string;
        limit?: number;
        offset?: number;
    }) => {
        const query = buildQuery(params || {});
        return fetchApi<TrendingListResponse>(`/api/trending/strategies${query}`);
    },

    get: (id: string) =>
        fetchApi<TrendingStrategy>(`/api/trending/strategies/${id}`),

    import: (id: string) =>
        fetchApi<{ strategy_id: string; message: string }>(`/api/trending/strategies/${id}/import`, {
            method: "POST",
        }),

    getStats: () =>
        fetchApi<{
            total_strategies: number;
            crypto_strategies: number;
            backtest_completed: number;
            backtest_pending: number;
        }>("/api/trending/stats"),
};

// ============== Admin Ops API ==============

export const adminOpsApi = {
    getQueue: (params?: { head_n?: number }) =>
        fetchApi<{ queue_name: string; length: number; head: string[] }>(
            `/api/admin/queue${buildQuery({ head_n: params?.head_n })}`
        ),

    listJobs: (params?: { limit?: number; types?: string }) =>
        fetchApi<{
            jobs: Array<{
                id: string;
                type: string;
                status: JobStatus;
                created_at: string;
                started_at?: string;
                finished_at?: string;
                error_message?: string;
                last_log?: string | null;
            }>;
        }>(`/api/admin/jobs${buildQuery({ limit: params?.limit, types: params?.types })}`),

    getJobLogs: (jobId: string, params?: { tail?: number }) =>
        fetchApi<{ job_id: string; lines: string[] }>(
            `/api/admin/jobs/${jobId}/logs${buildQuery({ tail: params?.tail })}`
        ),

    cancelJob: (jobId: string) =>
        fetchApi<{ job_id: string; status: JobStatus }>(`/api/admin/jobs/${jobId}/cancel`, {
            method: "POST",
        }),

    listTrendingStrategies: (params?: { limit?: number }) =>
        fetchApi<{
            items: Array<{
                id: string;
                source_type: string;
                tradingview_id: string;
                title: string;
                url: string;
                likes: number;
                views: number;
                comments: number;
                scraped_at: string;
                backtest_status: string;
                template_id?: string | null;
            }>;
        }>(`/api/admin/trending/strategies${buildQuery({ limit: params?.limit })}`),

    deleteTrendingStrategy: (tradingviewId: string) =>
        fetchApi<{ ok: boolean }>(`/api/admin/trending/strategies`, {
            method: "DELETE",
            body: JSON.stringify({ tradingview_id: tradingviewId }),
        }),
};

// ============== Templates API ==============

export const templatesApi = {
    list: (params?: {
        template_type?: string;
        featured?: boolean;
        search?: string;
        sort?: string;
        limit?: number;
        offset?: number;
    }) => {
        const query = buildQuery(params || {});
        return fetchApi<TemplateListResponse>(`/api/templates${query}`);
    },

    get: (id: string) =>
        fetchApi<TemplateDetail>(`/api/templates/${id}`),

    fork: (templateId: string, req: ForkTemplateRequest) =>
        fetchApi<ForkTemplateResponse>(`/api/templates/${templateId}/fork`, {
            method: "POST",
            body: JSON.stringify(req),
        }),

    subscribe: (templateId: string, req: SubscribeRequest) =>
        fetchApi<SubscribeResponse>(`/api/templates/${templateId}/subscribe`, {
            method: "POST",
            body: JSON.stringify(req),
        }),

    unsubscribe: (templateId: string) =>
        fetchApi<{ message: string }>(`/api/templates/${templateId}/unsubscribe`, {
            method: "DELETE",
        }),

    getPerformance: (templateId: string) =>
        fetchApi<TemplatePerformanceResponse>(`/api/templates/${templateId}/performance`),

    getPerformanceCharts: (templateId: string) =>
        fetchApi<PerformanceChartResponse>(`/api/templates/${templateId}/performance/charts`),

    triggerPerformanceUpdate: (templateId: string) =>
        fetchApi<{ message: string; template_id: string }>(`/api/templates/${templateId}/performance/trigger`, {
            method: "POST",
        }),

    getPerformanceRunDetail: (runId: string) =>
        fetchApi<TemplatePerformanceRunDetailResponse>(`/api/templates/performance/runs/${runId}`),
};

// ============== Subscriptions API ==============

export const subscriptionsApi = {
    list: () =>
        fetchApi<SubscriptionListResponse>("/api/subscriptions"),

    get: (subscriptionId: string) =>
        fetchApi<SubscriptionResponse>(`/api/subscriptions/${subscriptionId}`),

    sync: (subscriptionId: string) =>
        fetchApi<SyncResultResponse>(`/api/subscriptions/${subscriptionId}/sync`, {
            method: "POST",
        }),

    updateConfig: (subscriptionId: string, req: UserConfigUpdateRequest) =>
        fetchApi<SubscriptionResponse>(`/api/subscriptions/${subscriptionId}/config`, {
            method: "PATCH",
            body: JSON.stringify(req),
        }),

    pause: (subscriptionId: string) =>
        fetchApi<SubscriptionResponse>(`/api/subscriptions/${subscriptionId}/pause`, {
            method: "POST",
        }),

    resume: (subscriptionId: string) =>
        fetchApi<SubscriptionResponse>(`/api/subscriptions/${subscriptionId}/resume`, {
            method: "POST",
        }),

    // Telegram configuration
    testTelegram: (subscriptionId: string, req: { bot_token_encrypted: string; chat_id: string }) =>
        fetchApi<TelegramTestResponse>(`/api/subscriptions/${subscriptionId}/telegram/test`, {
            method: "POST",
            body: JSON.stringify(req),
        }),

    updateTelegramConfig: (subscriptionId: string, req: TelegramConfigUpdateRequest) =>
        fetchApi<SubscriptionResponse>(`/api/subscriptions/${subscriptionId}/telegram/config`, {
            method: "PATCH",
            body: JSON.stringify(req),
        }),

    deleteTelegramConfig: (subscriptionId: string) =>
        fetchApi<SubscriptionResponse>(`/api/subscriptions/${subscriptionId}/telegram/config`, {
            method: "DELETE",
        }),
};

// ============== Trading API ==============
export * from "./api/trading";
