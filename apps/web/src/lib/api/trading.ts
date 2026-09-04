/**
 * API client for trading endpoints
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

interface TradingConfigRequest {
    exchange: string;
    symbol?: string;
    symbols?: string[];
    intervals?: string[];
    account_id: string;
    max_position_pct: number;
    stop_loss_pct: number;
    leverage?: number;
}

interface TradingConfig {
    id: string;
    strategy_id: string;
    exchange: string;
    symbol: string;
    symbols?: string[];
    intervals?: string[];
    account_id?: string;
    max_position_pct: number;
    stop_loss_pct: number;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

interface TradingSession {
    id: string;
    config_id: string;
    exchange_account_id?: string;
    status: string;
    started_at: string;
    stopped_at?: string;
    total_pnl: number;
    total_trades: number;
    error_message?: string;
}

interface TradingStatus {
    config: TradingConfig | null;
    active_session: TradingSession | null;
    is_trading: boolean;
}

interface Position {
    id: string;
    session_id: string;
    symbol: string;
    side: string;
    size: number;
    entry_price: number;
    current_price: number;
    unrealized_pnl: number;
    realized_pnl: number;
    status: string;
    opened_at: string;
    closed_at?: string;
}

interface Order {
    id: string;
    session_id: string;
    exchange_order_id?: string;
    symbol: string;
    side: string;
    order_type: string;
    price?: number;
    size: number;
    filled_size: number;
    avg_fill_price?: number;
    status: string;
    created_at: string;
}

interface SymbolInfo {
    symbol: string;
    base_coin: string;
    quote_coin: string;
    contract_type: string;
}

interface SymbolsListResponse {
    symbols: SymbolInfo[];
    total: number;
}

async function fetchApi(path: string, options: RequestInit = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
        credentials: "include",
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...options.headers,
        },
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

export const tradingApi = {
    /**
     * Create or update trading configuration
     */
    async createConfig(strategyId: string, config: TradingConfigRequest): Promise<TradingConfig> {
        return fetchApi(`/api/strategies/${strategyId}/trading/config`, {
            method: "POST",
            body: JSON.stringify(config),
        });
    },

    /**
     * Get trading configuration
     */
    async getConfig(strategyId: string): Promise<TradingConfig | null> {
        try {
            return await fetchApi(`/api/strategies/${strategyId}/trading/config`);
        } catch (error) {
            // Return null if config doesn't exist
            return null;
        }
    },

    /**
     * Delete trading configuration
     */
    async deleteConfig(strategyId: string): Promise<void> {
        return fetchApi(`/api/strategies/${strategyId}/trading/config`, {
            method: "DELETE",
        });
    },

    /**
     * Start trading session
     */
    async startTrading(strategyId: string, accountId: string): Promise<TradingSession> {
        return fetchApi(`/api/strategies/${strategyId}/trading/start`, {
            method: "POST",
            body: JSON.stringify({ account_id: accountId }),
        });
    },

    /**
     * Stop trading session
     */
    async stopTrading(strategyId: string): Promise<TradingSession> {
        return fetchApi(`/api/strategies/${strategyId}/trading/stop`, {
            method: "POST",
        });
    },

    /**
     * Get trading status
     */
    async getStatus(strategyId: string): Promise<TradingStatus> {
        return fetchApi(`/api/strategies/${strategyId}/trading/status`);
    },

    /**
     * Get positions for a session
     */
    async getPositions(sessionId: string): Promise<Position[]> {
        return fetchApi(`/api/trading/sessions/${sessionId}/positions`);
    },

    /**
     * Get orders for a session
     */
    async getOrders(sessionId: string): Promise<Order[]> {
        return fetchApi(`/api/trading/sessions/${sessionId}/orders`);
    },

    /**
     * Get all trading sessions for a strategy
     */
    async getSessions(strategyId: string): Promise<TradingSession[]> {
        return fetchApi(`/api/strategies/${strategyId}/trading/sessions`);
    },

    /**
     * Get available trading symbols from exchange
     */
    async listSymbols(exchange: string = "okx", limit: number = 50): Promise<SymbolsListResponse> {
        const params = new URLSearchParams({
            exchange,
            limit: limit.toString(),
        });
        return fetchApi(`/api/symbols?${params}`);
    },
};

export type {
    TradingConfig,
    TradingConfigRequest,
    TradingSession,
    TradingStatus,
    Position,
    Order,
    SymbolInfo,
    SymbolsListResponse,
};
