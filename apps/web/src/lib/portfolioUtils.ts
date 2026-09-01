// Portfolio data aggregation utilities
import type { PortfolioSummary, OrderData, PositionHistoryData } from "./api";

// Helper function to sum array values
const sum = (values: number[]): number => {
  return values.reduce((acc, val) => acc + val, 0);
};

/**
 * Aggregate balance data from multiple accounts
 */
export function aggregateBalances(summaries: PortfolioSummary[]): PortfolioSummary["balance"] | null {
  const validBalances = summaries
    .map((s) => s.balance)
    .filter((b): b is NonNullable<typeof b> => b !== null && b !== undefined);

  if (validBalances.length === 0) return null;

  return {
    total_equity: sum(validBalances.map((b) => b.total_equity)),
    available: sum(validBalances.map((b) => b.available)),
    frozen: sum(validBalances.map((b) => b.frozen)),
    unrealized_pnl: sum(validBalances.map((b) => b.unrealized_pnl)),
    margin_used: sum(validBalances.map((b) => b.margin_used)),
  };
}

/**
 * Aggregate positions from multiple accounts
 * Keeps account_id for tracking which account each position belongs to
 */
export function aggregatePositions(
  summaries: Array<{ accountId: string; summary: PortfolioSummary }>
) {
  return summaries.flatMap(({ accountId, summary }) =>
    summary.positions.map((pos) => ({
      ...pos,
      account_id: accountId,
    }))
  );
}

/**
 * Aggregate orders from multiple accounts and sort by creation time
 */
export function aggregateOrders(
  ordersByAccount: Array<{ accountId: string; orders: OrderData[] }>
): OrderData[] {
  const allOrders = ordersByAccount.flatMap(({ accountId, orders }) =>
    orders.map((order) => ({
      ...order,
      account_id: accountId,
    }))
  );

  // Sort by created_at descending (newest first)
  return allOrders.sort((a, b) => {
    const dateA = new Date(a.created_at).getTime();
    const dateB = new Date(b.created_at).getTime();
    return dateB - dateA;
  });
}

/**
 * Aggregate position history from multiple accounts
 */
export function aggregatePositionHistory(
  positionsByAccount: Array<{ accountId: string; positions: PositionHistoryData[] }>
): PositionHistoryData[] {
  const allPositions = positionsByAccount.flatMap(({ accountId, positions }) =>
    positions.map((pos) => ({
      ...pos,
      account_id: accountId,
    }))
  );

  // Sort by closed_at descending (newest first)
  return allPositions.sort((a, b) => {
    const dateA = new Date(a.closed_at).getTime();
    const dateB = new Date(b.closed_at).getTime();
    return dateB - dateA;
  });
}

/**
 * Create aggregated portfolio summary from multiple account summaries
 */
export function aggregateSummaries(summaries: PortfolioSummary[]): PortfolioSummary {
  const balance = aggregateBalances(summaries);

  // Aggregate positions (flatten all positions from all accounts)
  const positions = summaries.flatMap((s) => s.positions);

  // Calculate total PnL
  const total_pnl = sum(summaries.map((s) => s.total_pnl));

  // Calculate total trades
  const total_trades = sum(summaries.map((s) => s.total_trades));

  // Check if any account has trading config
  const has_trading_config = summaries.some((s) => s.has_trading_config);

  // Check if any account has active session
  const has_active_session = summaries.some((s) => s.has_active_session);

  return {
    has_trading_config,
    has_active_session,
    balance,
    positions,
    total_pnl,
    total_trades,
  };
}

/**
 * Handle Promise.allSettled results and extract successful values
 */
export function handlePartialResults<T>(
  results: PromiseSettledResult<T>[]
): { successful: T[]; failed: number } {
  const successful = results
    .filter((r): r is PromiseFulfilledResult<T> => r.status === "fulfilled")
    .map((r) => r.value);

  const failed = results.filter((r) => r.status === "rejected").length;

  return { successful, failed };
}

/**
 * Get exchange emoji based on exchange name
 */
export function getExchangeEmoji(exchange: string): string {
  const exchangeEmojis: Record<string, string> = {
    okx: "🟢",
    binance: "🟡",
    bybit: "🟠",
    bitget: "🔵",
    gate: "🔴",
    kucoin: "🟣",
  };

  return exchangeEmojis[exchange.toLowerCase()] || "⚪";
}

/**
 * Calculate total balance across all accounts
 */
export function calculateTotalBalance(summaries: PortfolioSummary[]): number {
  const balance = aggregateBalances(summaries);
  return balance?.total_equity || 0;
}

/**
 * Calculate total unrealized PnL across all accounts
 */
export function calculateTotalUnrealizedPnl(summaries: PortfolioSummary[]): number {
  const balance = aggregateBalances(summaries);
  return balance?.unrealized_pnl || 0;
}
