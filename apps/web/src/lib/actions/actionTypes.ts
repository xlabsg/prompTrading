import React from "react";
import type { Strategy } from "@/lib/types";

export type ActionStatus = "idle" | "running" | "succeeded" | "failed";

export interface ActionPayload<P = Record<string, any>, R = Record<string, any>> {
    id: string;
    type: string;
    title: string;
    status: ActionStatus;
    params: P;
    result?: R;
    error?: string;
    createdAt: number;
    completedAt?: number;
}

export interface ActionContext {
    strategy: Strategy | null;
    queryClient: any;
    onNavigateView?: (view: "overview" | "code" | "backtest" | "live" | "portfolio" | "logs" | "signals", targetId?: string) => void;
    onSendMessage?: (message: string) => void;
}

export interface ActionCardProps<P = any, R = any> {
    payload: ActionPayload<P, R>;
    context: ActionContext;
    onRetry?: () => void;
}

export interface ActionHandler<P = any, R = any> {
    type: string;
    
    // 执行具体的动作，返回任务标识或直接结果
    execute: (context: ActionContext, params: P) => Promise<{ jobId?: string; result?: R }>;
    
    // 异步长时间任务等待（如回测、实盘部署等）
    pollCompletion?: (context: ActionContext, jobId: string, params: P) => Promise<R>;
    
    // 渲染卡片视图
    renderRunning: (props: ActionCardProps<P, R>) => React.ReactNode;
    renderSuccess: (props: ActionCardProps<P, R>) => React.ReactNode;
    renderError: (props: ActionCardProps<P, R>) => React.ReactNode;
}
