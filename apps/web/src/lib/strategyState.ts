import type { Strategy } from "@/lib/types";

/** True while a chat turn is running the agent against an already-generated strategy. */
export function isChatRefineTurn(strategy?: Strategy | null): boolean {
    return strategy?.active_job?.payload?.mode === "autonomous_chat_refine";
}

/** True while the agent is generating the workspace overview for a finished strategy. */
export function isOverviewGeneration(strategy?: Strategy | null): boolean {
    return strategy?.active_job?.payload?.mode === "generate_overview";
}

/**
 * Any agent container run against a strategy whose code already exists.
 *
 * These flip `chat_status` to `generating` for the duration of the run, but they
 * are not a strategy (re)generation, so views must not fall back to the
 * generation experience for them.
 */
export function isBackgroundAgentTurn(strategy?: Strategy | null): boolean {
    return isChatRefineTurn(strategy) || isOverviewGeneration(strategy);
}

/**
 * True once the strategy has code to show.
 *
 * `chat_status` is not this question: a chat refine turn flips it to `generating`
 * for the duration of the agent run, and gating views on `done` alone made the
 * backtest and code views blank out -- history included -- every time the user
 * sent a message.
 */
export function hasGeneratedCode(strategy?: Strategy | null): boolean {
    if (!strategy) return false;
    return strategy.chat_status === "done" || isBackgroundAgentTurn(strategy);
}
