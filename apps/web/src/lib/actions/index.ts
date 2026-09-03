import { actionRegistry } from "./actionRegistry";
import { BacktestActionHandler } from "./handlers/BacktestActionHandler";
import { MetricsComparisonActionHandler } from "./handlers/MetricsComparisonHandler";

// Register default handlers
actionRegistry.register(new BacktestActionHandler());
actionRegistry.register(new MetricsComparisonActionHandler());

export * from "./actionTypes";
export * from "./actionRegistry";
export * from "./actionParser";
export * from "./handlers/BacktestActionHandler";
export * from "./handlers/MetricsComparisonHandler";
