import type { Strategy } from "@/lib/types";

/** True while a chat turn is running the agent against an already-generated strategy. */
export function isChatRefineTurn(strategy?: Strategy | null): boolean {
    return strategy?.active_job?.payload?.mode === "autonomous_chat_refine";
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
    return strategy.chat_status === "done" || isChatRefineTurn(strategy);
}
