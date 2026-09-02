import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
    Wallet,
    Plus,
    EyeOff,
    Eye,
    Trash2,
    CheckCircle2,
    Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { exchangeAccountsApi } from "@/lib/api";
import type { ExchangeAccountResponse } from "@/lib/types";
import { useTranslation } from "react-i18next";

interface ExchangeAccountsDialogProps {
    strategyId: string;
    children: React.ReactNode;
}

const exchanges = [
    { id: "okx", name: "OKX", logo: "🟢", enabled: true },
    { id: "binance", name: "Binance", logo: "🟡", enabled: false, comingSoon: true },
];

const ExchangeAccountsDialog = ({ strategyId, children }: ExchangeAccountsDialogProps) => {
    const { t } = useTranslation();
    const queryClient = useQueryClient();
    const [isAddingNew, setIsAddingNew] = useState(false);
    const [newAccountName, setNewAccountName] = useState("");
    const [selectedExchange, setSelectedExchange] = useState("");
    const [apiKey, setApiKey] = useState("");
    const [secretKey, setSecretKey] = useState("");
    const [passphrase, setPassphrase] = useState("");
    const [showSecretKey, setShowSecretKey] = useState(false);
    const [showPassphrase, setShowPassphrase] = useState(false);

    const { data: accounts = [], isLoading } = useQuery({
        queryKey: ["exchange-accounts", strategyId],
        queryFn: () => exchangeAccountsApi.list(strategyId),
    });

    const createMutation = useMutation({
        mutationFn: () =>
            exchangeAccountsApi.create(strategyId, {
                name: newAccountName,
                exchange: selectedExchange,
                api_key: apiKey,
                api_secret: secretKey,
                api_passphrase: passphrase || undefined,
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["exchange-accounts", strategyId] });
            resetForm();
        },
    });

    const deleteMutation = useMutation({
        mutationFn: (accountId: string) => exchangeAccountsApi.remove(strategyId, accountId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["exchange-accounts", strategyId] });
        },
    });

    const resetForm = () => {
        setIsAddingNew(false);
        setNewAccountName("");
        setSelectedExchange("");
        setApiKey("");
        setSecretKey("");
        setPassphrase("");
    };

    const handleAddAccount = () => {
        if (!newAccountName || !selectedExchange || !apiKey || !secretKey || !passphrase) return;
        createMutation.mutate();
    };

    const renderAccountRow = (account: ExchangeAccountResponse) => {
        const exchange = exchanges.find((item) => item.id === account.exchange);
        return (
            <motion.div
                key={account.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-between p-4 rounded-md bg-muted/50 border border-border"
            >
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-background border border-border flex items-center justify-center text-lg">
                        {exchange?.logo}
                    </div>
                    <div>
                        <div className="font-medium text-foreground flex items-center gap-2">
                            {account.name}
                            {account.is_connected && (
                                <span className="w-2 h-2 rounded-full bg-long" />
                            )}
                        </div>
                        <div className="text-sm text-muted-foreground">
                            {exchange?.name || account.exchange}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => deleteMutation.mutate(account.id)}
                    >
                        <Trash2 size={14} />
                    </Button>
                </div>
            </motion.div>
        );
    };

    return (
        <Dialog>
            <DialogTrigger asChild>{children}</DialogTrigger>
            <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Wallet size={20} />
                        {t("exchangeAccounts.title")}
                    </DialogTitle>
                    <DialogDescription>
                        {t("exchangeAccounts.subtitle")}
                    </DialogDescription>
                </DialogHeader>

                <div className="flex-1 overflow-y-auto space-y-4 py-4">
                    {isLoading && (
                        <div className="flex items-center justify-center py-6 text-muted-foreground">
                            <Loader2 className="w-5 h-5 animate-spin" />
                        </div>
                    )}

                    {accounts.length > 0 && (
                        <div className="space-y-3">
                            <Label className="text-muted-foreground">{t("exchangeAccounts.connected")}</Label>
                            {accounts.map(renderAccountRow)}
                        </div>
                    )}

                    {isAddingNew ? (
                        <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            className="p-4 rounded-md border border-primary/50 bg-primary/5 space-y-4"
                        >
                            <div className="flex items-center justify-between">
                                <h3 className="font-medium text-foreground">{t("exchangeAccounts.addTitle")}</h3>
                                <Button variant="ghost" size="sm" onClick={resetForm}>
                                    {t("common.cancel")}
                                </Button>
                            </div>

                            <div className="grid gap-4">
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label>{t("exchangeAccounts.accountName")}</Label>
                                        <Input
                                            placeholder={t("exchangeAccounts.accountNamePlaceholder")}
                                            value={newAccountName}
                                            onChange={(e) => setNewAccountName(e.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>{t("exchangeAccounts.exchange")}</Label>
                                        <Select value={selectedExchange} onValueChange={setSelectedExchange}>
                                            <SelectTrigger>
                                                <SelectValue placeholder={t("exchangeAccounts.selectExchange")} />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {exchanges.filter(e => e.enabled).map((exchange) => (
                                                    <SelectItem key={exchange.id} value={exchange.id}>
                                                        <div className="flex items-center gap-2">
                                                            <span>{exchange.logo}</span>
                                                            <span>{exchange.name}</span>
                                                        </div>
                                                    </SelectItem>
                                                ))}
                                                {exchanges.filter(e => !e.enabled).map((exchange) => (
                                                    <div
                                                        key={exchange.id}
                                                        className="relative flex w-full cursor-not-allowed select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none opacity-50"
                                                    >
                                                        <div className="flex items-center gap-2">
                                                            <span>{exchange.logo}</span>
                                                            <span>{exchange.name}</span>
                                                            <span className="ml-auto text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                                                                {t("exchangeAccounts.comingSoon")}
                                                            </span>
                                                        </div>
                                                    </div>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label>{t("exchangeAccounts.apiKey")}</Label>
                                    <Input
                                        type="text"
                                        placeholder={t("exchangeAccounts.apiKeyPlaceholder")}
                                        value={apiKey}
                                        onChange={(e) => setApiKey(e.target.value)}
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label>{t("exchangeAccounts.secretKey")}</Label>
                                    <div className="relative">
                                        <Input
                                            type={showSecretKey ? "text" : "password"}
                                            placeholder={t("exchangeAccounts.secretKeyPlaceholder")}
                                            value={secretKey}
                                            onChange={(e) => setSecretKey(e.target.value)}
                                            className="pr-10"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShowSecretKey(!showSecretKey)}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                                        >
                                            {showSecretKey ? <EyeOff size={16} /> : <Eye size={16} />}
                                        </button>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label>{t("exchangeAccounts.passphrase")} <span className="text-destructive">*</span></Label>
                                    <div className="relative">
                                        <Input
                                            type={showPassphrase ? "text" : "password"}
                                            placeholder={t("exchangeAccounts.passphrasePlaceholder")}
                                            value={passphrase}
                                            onChange={(e) => setPassphrase(e.target.value)}
                                            className="pr-10"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShowPassphrase(!showPassphrase)}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                                        >
                                            {showPassphrase ? <EyeOff size={16} /> : <Eye size={16} />}
                                        </button>
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                    <CheckCircle2 size={14} className={cn(createMutation.isPending ? "text-muted-foreground" : "text-long")} />
                                    {t("exchangeAccounts.secureNotice")}
                                </div>
                                <Button onClick={handleAddAccount} disabled={createMutation.isPending}>
                                    {createMutation.isPending ? t("exchangeAccounts.saving") : t("exchangeAccounts.save")}
                                </Button>
                            </div>
                        </motion.div>
                    ) : (
                        <Button
                            variant="outline"
                            className="w-full gap-2"
                            type="button"
                            onClick={() => setIsAddingNew(true)}
                        >
                            <Plus size={16} />
                            {t("exchangeAccounts.addButton")}
                        </Button>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
};

export default ExchangeAccountsDialog;
