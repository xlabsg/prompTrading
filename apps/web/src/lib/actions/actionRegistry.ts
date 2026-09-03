import { ActionHandler } from "./actionTypes";

class ActionRegistry {
    private handlers: Map<string, ActionHandler> = new Map();

    register(handler: ActionHandler): void {
        this.handlers.set(handler.type, handler);
    }

    get(type: string): ActionHandler | undefined {
        return this.handlers.get(type);
    }

    has(type: string): boolean {
        return this.handlers.has(type);
    }

    getAll(): ActionHandler[] {
        return Array.from(this.handlers.values());
    }
}

export const actionRegistry = new ActionRegistry();
