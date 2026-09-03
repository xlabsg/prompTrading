import { ActionPayload } from "./actionTypes";

/**
 * Parses user message or LLM text for executable action requests.
 * Supports:
 * 1. Structured action blocks (e.g. ```action:backtest ... ``` or JSON with __action__)
 * 2. Natural language fallback intent detection (e.g. "启动回测", "跑一下回测", "run backtest")
 */
export function parseActionFromMessage(text: string): ActionPayload | null {
    if (!text || typeof text !== "string") return null;

    const trimmed = text.trim();

    // 1. Check for structured action block: ```action:TYPE \n JSON \n ```
    const actionBlockMatch = trimmed.match(/```action:([a-zA-Z0-9_-]+)\s*([\s\S]*?)```/);
    if (actionBlockMatch) {
        const type = actionBlockMatch[1];
        let params = {};
        try {
            params = JSON.parse(actionBlockMatch[2].trim());
        } catch {
            // ignore JSON parse error, fallback to empty params
        }
        return {
            id: `action_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
            type,
            title: `Action: ${type}`,
            status: "running",
            params,
            createdAt: Date.now(),
        };
    }

    // 2. Natural language intent matching for Backtest (Zero-friction)
    // Matches: "回测", "跑回测", "执行回测", "用ETH测试一下近3个月回测", "run backtest", etc.
    const backtestKeywords = [
        /(?:跑|执行|开始|启动|进行|做|测|测试)[\s\S]{0,15}回测/,
        /(?:run|start|execute|perform)[\s\S]{0,15}backtest/i,
        /回测/,
        /\bbacktest\b/i,
    ];

    const isBacktestIntent = backtestKeywords.some((regex) => regex.test(trimmed));
    if (isBacktestIntent) {
        // Extract optional symbol
        let symbol = "BTC-USDT";
        if (/ETH/i.test(trimmed)) symbol = "ETH-USDT";
        else if (/SOL/i.test(trimmed)) symbol = "SOL-USDT";
        else if (/BNB/i.test(trimmed)) symbol = "BNB-USDT";

        // Extract optional date range
        let range = "30d";
        if (/90\s*(?:天|day|d)|(?:3|三)个?月/i.test(trimmed)) range = "90d";
        else if (/180\s*(?:天|day|d)|(?:6|六)个?月/i.test(trimmed)) range = "180d";
        else if (/1\s*(?:年|year|y)|365\s*(?:天|day|d)/i.test(trimmed)) range = "1y";

        return {
            id: `action_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
            type: "backtest",
            title: "策略回测",
            status: "running",
            params: {
                symbol,
                range,
                exchange: "okx",
                interval: "1h",
                initial_cash: 10000,
            },
            createdAt: Date.now(),
        };
    }

    return null;
}
