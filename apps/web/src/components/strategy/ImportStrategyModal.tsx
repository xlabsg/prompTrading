import { useCallback, useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Download, Loader2, Youtube, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";
import { useNavigate } from "react-router-dom";
import { apiBaseUrl, jobsApi } from "@/lib/api";
import type { Job } from "@/lib/types";
import { useTranslation } from "react-i18next";

interface ImportStrategyModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

type ImportStep = "idle" | "submitting" | "processing" | "success" | "error";

type ImportSource = "tradingview" | "youtube";

interface ImportResponse {
    job: {
        id: string;
        status: string;
    };
    strategy: {
        id: string;
        name: string;
    };
    source_metadata?: {
        source_type: string;
        script_name?: string;
        script_author?: string;
    };
}

const ImportStrategyModal = ({ open, onOpenChange }: ImportStrategyModalProps) => {
    const { toast } = useToast();
    const navigate = useNavigate();
    const { t } = useTranslation();

    // TradingView state
    const [tradingViewUrl, setTradingViewUrl] = useState("");
    const [tradingViewName, setTradingViewName] = useState("");

    // YouTube state
    const [youtubeUrl, setYoutubeUrl] = useState("");
    const [youtubeName, setYoutubeName] = useState("");

    // Import progress state
    const [importStep, setImportStep] = useState<ImportStep>("idle");
    const [currentJobId, setCurrentJobId] = useState<string | null>(null);
    const [importSource, setImportSource] = useState<ImportSource>("tradingview");
    const [strategyId, setStrategyId] = useState<string | null>(null);
    const [strategyName, setStrategyName] = useState<string>("");
    const [progressMessage, setProgressMessage] = useState<string>("");
    const [errorMessage, setErrorMessage] = useState<string>("");

    // Reset state when modal opens/closes
    useEffect(() => {
        if (!open) {
            setImportStep("idle");
            setCurrentJobId(null);
            setStrategyId(null);
            setStrategyName("");
            setProgressMessage("");
            setErrorMessage("");
        }
    }, [open]);

    // Get progress message based on job status
    const getJobProgressMessage = useCallback((job: Job): string => {
        switch (job.status) {
            case "queued":
                return t("importStrategy.progress.queued");
            case "running":
                return importSource === "tradingview"
                    ? t("importStrategy.progress.processingStrategy")
                    : t("importStrategy.progress.processingVideo");
            case "succeeded":
                return t("importStrategy.progress.complete");
            case "failed":
                return t("importStrategy.progress.failed");
            default:
                return t("importStrategy.progress.processing");
        }
    }, [importSource, t]);

    // Handle import success
    const handleImportSuccess = useCallback((job: Job, strategyId: string) => {
        setImportStep("success");
        setProgressMessage(t("importStrategy.progress.complete"));

        toast({
            title: t("importStrategy.toast.successTitle"),
            description: t("importStrategy.toast.successDesc", { name: strategyName }),
        });

        // Close modal and navigate after a short delay
        setTimeout(() => {
            onOpenChange(false);
            navigate(`/strategy/${strategyId}`);
        }, 1000);
    }, [strategyName, toast, onOpenChange, navigate, t]);

    // Handle import error
    const handleImportError = useCallback((error: Error) => {
        setImportStep("error");
        setErrorMessage(error.message || t("importStrategy.toast.errorDesc"));

        toast({
            title: t("importStrategy.toast.errorTitle"),
            description: error.message,
            variant: "destructive",
        });
    }, [toast, t]);

    // Handle cancel
    const handleCancel = useCallback(() => {
        // Just close the modal - the job will continue in background
        onOpenChange(false);
    }, [onOpenChange]);

    // Poll job status when in processing state
    useEffect(() => {
        if (currentJobId && importStep === "processing" && strategyId) {
            let aborted = false;

            const pollJob = async () => {
                try {
                    const job = await jobsApi.waitForCompletion(
                        currentJobId,
                        (progressJob) => {
                            if (aborted) return;
                            setProgressMessage(getJobProgressMessage(progressJob));
                        },
                        2000,   // 2 second interval
                        420000  // 7 minute timeout
                    );

                    if (aborted) return;

                    if (job.status === "succeeded") {
                        handleImportSuccess(job, strategyId);
                    } else if (job.status === "failed") {
                        handleImportError(new Error(job.error || t("importStrategy.toast.errorTitle")));
                    }
                } catch (error) {
                    if (aborted) return;
                    handleImportError(error as Error);
                }
            };

            pollJob();

            return () => {
                aborted = true;
            };
        }
    }, [currentJobId, importStep, strategyId, getJobProgressMessage, handleImportSuccess, handleImportError]);

    // TradingView import mutation
    const tradingViewMutation = useMutation({
        mutationFn: async (data: { url: string; strategy_name?: string }) => {
            const baseUrl = apiBaseUrl();
            const response = await fetch(`${baseUrl}/api/strategies/import/tradingview`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                credentials: "include",
                body: JSON.stringify(data),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || t("importStrategy.errors.tradingViewImport"));
            }

            return response.json() as Promise<ImportResponse>;
        },
        onSuccess: (data) => {
            const scriptName = data.source_metadata?.script_name || "";
            const author = data.source_metadata?.script_author || "";

            // Store import info and start polling
            setImportSource("tradingview");
            setStrategyId(data.strategy.id);
            setStrategyName(scriptName || tradingViewName || t("importStrategy.defaults.tradingViewName"));
            setCurrentJobId(data.job.id);
            setImportStep("processing");
            setProgressMessage(getJobProgressMessage(data.job));

            // Clear form
            setTradingViewUrl("");
            setTradingViewName("");
        },
        onError: (error: Error) => {
            toast({
                title: t("importStrategy.toast.errorTitle"),
                description: error.message,
                variant: "destructive",
            });
        },
    });

    // YouTube import mutation (placeholder)
    const youtubeMutation = useMutation({
        mutationFn: async (data: { url: string; strategy_name?: string }) => {
            const baseUrl = apiBaseUrl();
            const response = await fetch(`${baseUrl}/api/strategies/import/youtube`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                credentials: "include",
                body: JSON.stringify(data),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || t("importStrategy.errors.youtubeImport"));
            }

            return response.json() as Promise<ImportResponse>;
        },
        onSuccess: (data) => {
            // Store import info and start polling
            setImportSource("youtube");
            setStrategyId(data.strategy.id);
            setStrategyName(youtubeName || t("importStrategy.defaults.youtubeName"));
            setCurrentJobId(data.job.id);
            setImportStep("processing");
            setProgressMessage(getJobProgressMessage(data.job));

            // Clear form
            setYoutubeUrl("");
            setYoutubeName("");
        },
        onError: (error: Error) => {
            toast({
                title: t("importStrategy.toast.errorTitle"),
                description: error.message,
                variant: "destructive",
            });
        },
    });

    const handleTradingViewImport = () => {
        if (!tradingViewUrl.trim()) {
            toast({
                title: t("importStrategy.validation.urlRequiredTitle"),
                description: t("importStrategy.validation.tradingViewUrl"),
                variant: "destructive",
            });
            return;
        }

        setImportStep("submitting");
        tradingViewMutation.mutate({
            url: tradingViewUrl.trim(),
            strategy_name: tradingViewName.trim() || undefined,
        });
    };

    const handleYouTubeImport = () => {
        if (!youtubeUrl.trim()) {
            toast({
                title: t("importStrategy.validation.urlRequiredTitle"),
                description: t("importStrategy.validation.youtubeUrl"),
                variant: "destructive",
            });
            return;
        }

        setImportStep("submitting");
        youtubeMutation.mutate({
            url: youtubeUrl.trim(),
            strategy_name: youtubeName.trim() || undefined,
        });
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[600px]">
                {importStep === "processing" || importStep === "success" || importStep === "error" ? (
                    // Progress View
                    <>
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                {importStep === "success" ? (
                                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                                ) : importStep === "error" ? (
                                    <X className="w-5 h-5 text-destructive" />
                                ) : (
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                )}
                                {importStep === "processing" && t("importStrategy.status.processing")}
                                {importStep === "success" && t("importStrategy.status.success")}
                                {importStep === "error" && t("importStrategy.status.error")}
                            </DialogTitle>
                            <DialogDescription>
                                {importStep === "processing" && t("importStrategy.status.processingDesc", { name: strategyName })}
                                {importStep === "success" && t("importStrategy.status.successDesc", { name: strategyName })}
                                {importStep === "error" && t("importStrategy.status.errorDesc", { name: strategyName })}
                            </DialogDescription>
                        </DialogHeader>

                        <div className="py-6">
                            {importStep === "processing" && (
                                <div className="flex flex-col items-center text-center space-y-4">
                                    <Loader2 className="w-12 h-12 animate-spin text-primary" />
                                    <div className="space-y-2">
                                        <p className="text-sm font-medium">{progressMessage}</p>
                                        <p className="text-xs text-muted-foreground">
                                            {t("importStrategy.processingHint")}
                                        </p>
                                    </div>
                                </div>
                            )}

                            {importStep === "success" && (
                                <div className="flex flex-col items-center text-center space-y-4">
                                    <CheckCircle2 className="w-12 h-12 text-green-500" />
                                    <div className="space-y-2">
                                        <p className="text-sm font-medium">{t("importStrategy.successTitle")}</p>
                                        <p className="text-xs text-muted-foreground">
                                            {t("importStrategy.successSubtitle")}
                                        </p>
                                    </div>
                                </div>
                            )}

                            {importStep === "error" && (
                                <div className="flex flex-col items-center text-center space-y-4">
                                    <X className="w-12 h-12 text-destructive" />
                                    <div className="space-y-2">
                                        <p className="text-sm font-medium">{t("importStrategy.errorTitle")}</p>
                                        <p className="text-xs text-muted-foreground">{errorMessage}</p>
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="flex justify-end">
                            {importStep === "processing" && (
                                <Button variant="ghost" onClick={handleCancel}>
                                    {t("importStrategy.actions.runInBackground")}
                                </Button>
                            )}
                            {importStep === "error" && (
                                <Button onClick={() => setImportStep("idle")}>
                                    {t("importStrategy.actions.goBack")}
                                </Button>
                            )}
                        </div>
                    </>
                ) : (
                    // Form View
                    <>
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <Download className="w-5 h-5" />
                                {t("importStrategy.title")}
                            </DialogTitle>
                            <DialogDescription>
                                {t("importStrategy.subtitle")}
                            </DialogDescription>
                        </DialogHeader>

                        <Tabs defaultValue="tradingview" className="w-full">
                            <TabsList className="grid w-full grid-cols-1">
                                <TabsTrigger value="tradingview">
                                    <svg
                                        className="w-4 h-4 mr-2"
                                        viewBox="0 0 24 24"
                                        fill="currentColor"
                                    >
                                    <path d="M3 3h18v18H3V3zm15 6h-3v9h3v-9zM9 9H6v9h3V9zm6-3h-3v12h3V6z" />
                                </svg>
                                {t("importStrategy.sources.tradingview")}
                            </TabsTrigger>
                                {/* YouTube import temporarily disabled due to YouTube's restrictions */}
                                {/* <TabsTrigger value="youtube">
                                    <Youtube className="w-4 h-4 mr-2" />
                                    YouTube
                                </TabsTrigger> */}
                            </TabsList>

                            <TabsContent value="tradingview" className="space-y-4 mt-4">
                                <div className="space-y-2">
                                    <Label htmlFor="tv-url">{t("importStrategy.tradingview.urlLabel")}</Label>
                                    <Input
                                        id="tv-url"
                                        placeholder={t("importStrategy.tradingview.urlPlaceholder")}
                                        value={tradingViewUrl}
                                        onChange={(e) => setTradingViewUrl(e.target.value)}
                                        disabled={tradingViewMutation.isPending}
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        {t("importStrategy.tradingview.urlHint")}
                                    </p>
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="tv-name">{t("importStrategy.tradingview.nameLabel")}</Label>
                                    <Input
                                        id="tv-name"
                                        placeholder={t("importStrategy.tradingview.namePlaceholder")}
                                        value={tradingViewName}
                                        onChange={(e) => setTradingViewName(e.target.value)}
                                        disabled={tradingViewMutation.isPending}
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        {t("importStrategy.tradingview.nameHint")}
                                    </p>
                                </div>

                                <div className="rounded-lg bg-muted p-4 text-sm">
                                    <p className="font-medium mb-2">{t("importStrategy.howItWorks.title")}</p>
                                    <ol className="list-decimal list-inside space-y-1 text-muted-foreground">
                                        <li>{t("importStrategy.howItWorks.step1")}</li>
                                        <li>{t("importStrategy.howItWorks.step2")}</li>
                                        <li>{t("importStrategy.howItWorks.step3")}</li>
                                    </ol>
                                </div>

                                <Button
                                    onClick={handleTradingViewImport}
                                    disabled={tradingViewMutation.isPending}
                                    className="w-full"
                                >
                                    {tradingViewMutation.isPending ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            {t("importStrategy.actions.importing")}
                                        </>
                                    ) : (
                                        <>
                                            <Download className="mr-2 h-4 w-4" />
                                            {t("importStrategy.actions.importFromTradingView")}
                                        </>
                                    )}
                                </Button>
                            </TabsContent>

                            {/* YouTube import temporarily disabled */}
                            {/* <TabsContent value="youtube" className="space-y-4 mt-4">
                                <div className="space-y-2">
                                    <Label htmlFor="yt-url">YouTube Video URL *</Label>
                                    <Input
                                        id="yt-url"
                                        placeholder="https://www.youtube.com/watch?v=..."
                                        value={youtubeUrl}
                                        onChange={(e) => setYoutubeUrl(e.target.value)}
                                        disabled={youtubeMutation.isPending}
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Paste a YouTube video URL explaining a trading strategy (max 30 min)
                                    </p>
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="yt-name">Custom Strategy Name (Optional)</Label>
                                    <Input
                                        id="yt-name"
                                        placeholder="My Custom Strategy"
                                        value={youtubeName}
                                        onChange={(e) => setYoutubeName(e.target.value)}
                                        disabled={youtubeMutation.isPending}
                                    />
                                </div>

                                <div className="rounded-lg bg-muted p-4 text-sm">
                                    <p className="font-medium mb-2">How it works:</p>
                                    <ol className="list-decimal list-inside space-y-1 text-muted-foreground">
                                        <li>We download and transcribe the audio</li>
                                        <li>AI extracts the trading strategy logic</li>
                                        <li>Converts to Python backtesting code</li>
                                    </ol>
                                </div>

                                <Button
                                    onClick={handleYouTubeImport}
                                    disabled={youtubeMutation.isPending}
                                    className="w-full"
                                >
                                    {youtubeMutation.isPending ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Processing...
                                        </>
                                    ) : (
                                        <>
                                            <Youtube className="mr-2 h-4 w-4" />
                                            Import from YouTube
                                        </>
                                    )}
                                </Button>
                            </TabsContent> */}
                        </Tabs>
                    </>
                )}
            </DialogContent>
        </Dialog>
    );
};

export default ImportStrategyModal;
