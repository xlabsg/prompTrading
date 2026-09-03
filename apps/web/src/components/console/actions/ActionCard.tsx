import React from "react";
import { useTranslation } from "react-i18next";
import { actionRegistry } from "@/lib/actions/actionRegistry";
import { ActionPayload, ActionContext } from "@/lib/actions/actionTypes";

interface ActionCardProps {
    payload: ActionPayload;
    context: ActionContext;
    onRetry?: () => void;
}

export const ActionCard: React.FC<ActionCardProps> = ({ payload, context, onRetry }) => {
    const { t } = useTranslation();
    const handler = actionRegistry.get(payload.type);

    if (!handler) {
        return (
            <div className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
                {t("actions.unknownAction", { type: payload.type, defaultValue: `Unknown action: ${payload.type}` })}
            </div>
        );
    }

    if (payload.status === "running") {
        return <>{handler.renderRunning({ payload, context, onRetry })}</>;
    }

    if (payload.status === "succeeded") {
        return <>{handler.renderSuccess({ payload, context, onRetry })}</>;
    }

    if (payload.status === "failed") {
        return <>{handler.renderError({ payload, context, onRetry })}</>;
    }

    return null;
};
