import type { Strategy } from "@/lib/types";

const DEFAULT_GENERATION_PROMPT = "Generate a strategy based on user requirements.";

function collectUserMessages(strategy: Strategy | null | undefined): string[] {
    if (!strategy?.chat_history) return [];

    const userMessages: string[] = [];
    for (const message of strategy.chat_history) {
        if (message.role !== "user") continue;
        const content = String(message.content || "").trim();
        if (!content || content.startsWith("/")) continue;
        userMessages.push(content);
    }
    return userMessages;
}

function stringifyChatConfig(strategy: Strategy | null | undefined): string | null {
    if (!strategy?.chat_config) return null;
    try {
        return JSON.stringify(strategy.chat_config, null, 2);
    } catch {
        return null;
    }
}

export function buildGenerationPrompt(strategy: Strategy | null | undefined): string {
    const userMessages = collectUserMessages(strategy);
    let prompt = userMessages.join("\n\n").trim();

    const chatConfigJson = stringifyChatConfig(strategy);
    if (chatConfigJson) {
        const configHint =
            "Supplemental structured summary (reference only; user requirements above take precedence):\n" +
            chatConfigJson;
        prompt = prompt ? `${prompt}\n\n${configHint}` : configHint;
    }

    return prompt || DEFAULT_GENERATION_PROMPT;
}

