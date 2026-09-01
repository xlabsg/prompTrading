import { motion } from "framer-motion";
import { Wallet, Circle, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { ExchangeAccountResponse } from "@/lib/types";
import { getExchangeEmoji } from "@/lib/portfolioUtils";
import { useTranslation } from "react-i18next";

interface AccountSidebarProps {
  accounts: ExchangeAccountResponse[];
  selectedAccountId: string;
  onAccountChange: (accountId: string) => void;
  totalBalance: number;
  unrealizedPnl: number;
  collapsed: boolean;
  onToggleCollapse: () => void;
  accountBalances?: Map<string, number>; // Individual account balances
}

const AccountSidebar = ({
  accounts,
  selectedAccountId,
  onAccountChange,
  totalBalance,
  unrealizedPnl,
  collapsed,
  onToggleCollapse,
  accountBalances = new Map(),
}: AccountSidebarProps) => {
  const { t } = useTranslation();
  const formatCurrency = (num: number) => {
    return `$${num.toFixed(2)}`;
  };

  // Count connected accounts
  const connectedCount = accounts.filter((acc) => acc.is_connected).length;

  if (collapsed) {
    return (
      <motion.div
        initial={false}
        animate={{ width: 64 }}
        transition={{ duration: 0.3, ease: "easeInOut" }}
        className="border-r border-border bg-card/50 flex flex-col items-center py-4"
      >
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          className="mb-4"
        >
          <ChevronRight size={18} />
        </Button>

        {/* Mini account icons */}
        <div className="mt-4 space-y-2">
          {/* All Accounts icon */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onAccountChange("all")}
            className={cn(
              "w-10 h-10 rounded-lg transition-colors",
              selectedAccountId === "all"
                ? "bg-primary text-primary-foreground"
                : "hover:bg-muted"
            )}
          >
            <span className="text-lg">📊</span>
          </Button>

          {/* Individual accounts (show first 5) */}
          {accounts.slice(0, 5).map((acc) => (
            <Button
              key={acc.id}
              variant="ghost"
              size="icon"
              onClick={() => onAccountChange(acc.id)}
              className={cn(
                "w-10 h-10 rounded-lg transition-colors",
                selectedAccountId === acc.id
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted"
              )}
            >
              <span className="text-lg">{getExchangeEmoji(acc.exchange)}</span>
            </Button>
          ))}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={false}
      animate={{ width: 256 }}
      transition={{ duration: 0.3, ease: "easeInOut" }}
      className="border-r border-border bg-card/50 flex flex-col"
    >
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Wallet className="w-4 h-4 text-foreground" />
            <h2 className="font-semibold text-foreground">{t("portfolioView.sidebar.title")}</h2>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleCollapse}
            className="h-8 w-8"
          >
            <ChevronLeft size={16} />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          {t("portfolioView.sidebar.subtitle")}
        </p>
      </div>

      {/* Connection Status */}
      <div className="px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2 text-sm">
          <Circle
            className={cn(
              "w-2 h-2",
              connectedCount > 0
                ? "fill-green-500 text-green-500"
                : "fill-red-500 text-red-500"
            )}
          />
          <span className="text-muted-foreground">
            {connectedCount > 0 ? t("portfolioView.sidebar.connected") : t("portfolioView.sidebar.disconnected")}
          </span>
        </div>
      </div>

      {/* Total Balance Summary */}
      <div className="p-4 border-b border-border">
        <div className="text-xs text-muted-foreground">{t("portfolioView.sidebar.totalBalance")}</div>
        <div className="text-2xl font-bold text-foreground mt-1">
          {formatCurrency(totalBalance)}
        </div>
        <div className="flex items-center gap-1 mt-1">
          <span className="text-xs text-muted-foreground">{t("portfolioView.sidebar.unrealizedPnl")}</span>
          <span
            className={cn(
              "text-xs font-medium",
              unrealizedPnl >= 0 ? "text-green-500" : "text-red-500"
            )}
          >
            {unrealizedPnl >= 0 ? "+" : ""}
            {formatCurrency(unrealizedPnl)}
          </span>
        </div>
      </div>

      {/* Account List */}
      <ScrollArea className="flex-1">
        <div className="p-2">
          <div className="text-xs text-muted-foreground px-2 py-2">
            {t("portfolioView.sidebar.accountList")}
          </div>

          {/* All Accounts Option */}
          {accounts.length > 1 && (
            <button
              onClick={() => onAccountChange("all")}
              className={cn(
                "w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors mb-2",
                selectedAccountId === "all"
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted text-foreground"
              )}
            >
              <div
                className={cn(
                  "w-8 h-8 rounded-lg flex items-center justify-center text-lg",
                  selectedAccountId === "all"
                    ? "bg-primary-foreground/20"
                    : "bg-background/50"
                )}
              >
                📊
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm">{t("portfolioView.sidebar.allAccounts")}</div>
                <div
                  className={cn(
                    "text-xs",
                    selectedAccountId === "all"
                      ? "text-primary-foreground/70"
                      : "text-muted-foreground"
                  )}
                >
                  {formatCurrency(totalBalance)}
                </div>
              </div>
              <Badge
                variant={selectedAccountId === "all" ? "outline" : "secondary"}
                className={cn(
                  "text-xs px-1.5 py-0.5",
                  selectedAccountId === "all" &&
                    "border-primary-foreground/20 text-primary-foreground"
                )}
              >
                {accounts.length}
              </Badge>
            </button>
          )}

          {/* Individual Account Cards */}
          {accounts.map((acc) => {
            const balance = accountBalances.get(acc.id) || 0;

            return (
              <motion.button
                key={acc.id}
                onClick={() => onAccountChange(acc.id)}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2 }}
                whileHover={{ scale: 1.02 }}
                className={cn(
                  "w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors mb-2",
                  selectedAccountId === acc.id
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted text-foreground"
                )}
              >
                <div
                  className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center text-lg",
                    selectedAccountId === acc.id
                      ? "bg-primary-foreground/20"
                      : "bg-background/50"
                  )}
                >
                  {getExchangeEmoji(acc.exchange)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm truncate">{acc.name}</div>
                  <div
                    className={cn(
                      "text-xs flex items-center gap-1.5",
                      selectedAccountId === acc.id
                        ? "text-primary-foreground/70"
                        : "text-muted-foreground"
                    )}
                  >
                    <Circle
                      className={cn(
                        "w-1.5 h-1.5",
                        acc.is_connected
                          ? "fill-green-500 text-green-500"
                          : "fill-red-500 text-red-500"
                      )}
                    />
                    <span>{formatCurrency(balance)}</span>
                  </div>
                </div>
              </motion.button>
            );
          })}

          {/* Empty state */}
          {accounts.length === 0 && (
            <div className="text-center py-8 text-sm text-muted-foreground">
              {t("portfolioView.sidebar.emptyAccounts")}
            </div>
          )}
        </div>
      </ScrollArea>
    </motion.div>
  );
};

export default AccountSidebar;
