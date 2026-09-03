import { actionRegistry } from "./actionRegistry";
import { BacktestActionHandler } from "./handlers/BacktestActionHandler";

// Register default handlers
actionRegistry.register(new BacktestActionHandler());

export * from "./actionTypes";
export * from "./actionRegistry";
export * from "./actionParser";
export * from "./handlers/BacktestActionHandler";
