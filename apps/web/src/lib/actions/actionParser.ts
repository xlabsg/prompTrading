import { ActionPayload } from "./actionTypes";

/**
 * Parses Agent/LLM text for structured executable action blocks.
 * Protocol:
 * ```action:TYPE
 * { ...json params... }
 * ```
 */
export function parseActionFromMessage(text: string): ActionPayload | null {
    if (!text || typeof text !== "string") return null;

    const trimmed = text.trim();

    // Check for structured action block: ```action:TYPE \n JSON \n ```
    const actionBlockMatch = trimmed.match(/```action:([a-zA-Z0-9_-]+)\s*([\s\S]*?)```/);
    if (!actionBlockMatch) {
        return null;
    }

    const type = actionBlockMatch[1].trim();
    let params: Record<string, any> = {};
    const rawJson = actionBlockMatch[2].trim();

    if (rawJson) {
        try {
            params = JSON.parse(rawJson);
        } catch {
            console.warn(`[ActionParser] Failed to parse JSON params for action: ${type}`);
            params = {};
        }
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

