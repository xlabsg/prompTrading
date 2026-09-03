import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Strategy } from "@/pages/Console";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
    Radio,
    Shield,
    Zap,
    Bell,
    CheckCircle2,
    ArrowRight,
    Lock,
    Sparkles,
    LineChart,
    Code,
    Layers,
} from "lucide-react";
import { useTranslation } from "react-i18next";

interface LiveTradingViewProps {
    strategy: Strategy | null;
    onNavigateToPortfolio?: () => void;
    onNavigateToChat?: (message?: string) => void;
}

const WAITLIST_STORAGE_KEY = "promp_trading_live_waitlist_registered";

export const LiveTradingView = ({ strategy }: LiveTradingViewProps) => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const [email, setEmail] = useState("");
    const [isSubmitted, setIsSubmitted] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);

    useEffect(() => {
        if (typeof window !== "undefined") {
            const registered = localStorage.getItem(WAITLIST_STORAGE_KEY);
            if (registered) {
                setIsSubmitted(true);
            }
        }
    }, []);

    const handleJoinWaitlist = (e: React.FormEvent) => {
        e.preventDefault();
        if (!email.trim()) return;
        setIsSubmitting(true);
        setTimeout(() => {
            if (typeof window !== "undefined") {
                localStorage.setItem(WAITLIST_STORAGE_KEY, email.trim());
            }
            setIsSubmitting(false);
            setIsSubmitted(true);
        }, 500);
    };

    const roadmapFeatures = [
        {
            icon: Zap,
            title: t("liveTradingRoadmap.features.directApiTitle"),
            description: t("liveTradingRoadmap.features.directApiDesc"),
            badge: "Direct API",
        },
        {
            icon: Shield,
            title: t("liveTradingRoadmap.features.riskEngineTitle"),
            description: t("liveTradingRoadmap.features.riskEngineDesc"),
            badge: "Risk Engine",
        },
        {
            icon: Bell,
            title: t("liveTradingRoadmap.features.alertsTitle"),
            description: t("liveTradingRoadmap.features.alertsDesc"),
            badge: "Alerts",
        },
        {
            icon: Layers,
            title: t("liveTradingRoadmap.features.securityTitle"),
            description: t("liveTradingRoadmap.features.securityDesc"),
            badge: "Security",
        },
    ];

    return (
        <div className="h-full overflow-y-auto bg-gradient-to-b from-background via-muted/20 to-background p-6">
            <div className="max-w-4xl mx-auto space-y-8 py-4">
                {/* Hero Header */}
                <div className="text-center space-y-4">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 text-xs font-semibold">
                        <Sparkles size={13} />
                        <span>{t("liveTradingRoadmap.badge")}</span>
                    </div>

                    <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-foreground">
                        {t("liveTradingRoadmap.title")}
                    </h1>

                    <p className="text-muted-foreground text-base max-w-2xl mx-auto leading-relaxed">
                        {t("liveTradingRoadmap.description")}
                    </p>
                </div>

                {/* Waitlist Registration Card */}
                <Card className="border-primary/20 bg-gradient-to-br from-primary/5 via-card to-background shadow-lg overflow-hidden">
                    <CardHeader className="text-center pb-2">
                        <CardTitle className="text-xl font-bold flex items-center justify-center gap-2">
                            <Radio className="w-5 h-5 text-primary animate-pulse" />
                            <span>{t("liveTradingRoadmap.waitlistTitle")}</span>
                        </CardTitle>
                        <CardDescription className="text-sm">
                            {t("liveTradingRoadmap.waitlistDesc")}
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="pt-4 pb-6">
                        {isSubmitted ? (
                            <div className="flex flex-col items-center justify-center gap-2 p-6 rounded-xl bg-green-500/10 border border-green-500/20 text-green-700 dark:text-green-400 text-center">
                                <CheckCircle2 className="w-8 h-8 text-green-500" />
                                <div className="font-semibold text-base">{t("liveTradingRoadmap.waitlistSuccessTitle")}</div>
                                <div className="text-xs text-muted-foreground max-w-md">
                                    {t("liveTradingRoadmap.waitlistSuccessDesc")}
                                </div>
                            </div>
                        ) : (
                            <form onSubmit={handleJoinWaitlist} className="max-w-md mx-auto flex flex-col sm:flex-row gap-3">
                                <Input
                                    type="email"
                                    placeholder={t("liveTradingRoadmap.placeholder")}
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                    className="flex-1 bg-background"
                                />
                                <Button type="submit" disabled={isSubmitting} className="gap-2 shrink-0">
                                    <Sparkles size={15} />
                                    <span>{isSubmitting ? t("liveTradingRoadmap.submitting") : t("liveTradingRoadmap.submit")}</span>
                                </Button>
                            </form>
                        )}
                    </CardContent>
                </Card>

                {/* Architecture & Roadmap Highlights */}
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-bold text-foreground">{t("liveTradingRoadmap.roadmapTitle")}</h2>
                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <Lock size={12} />
                            {t("liveTradingRoadmap.roadmapSubtitle")}
                        </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {roadmapFeatures.map((item, index) => (
                            <Card key={index} className="border-border/60 bg-card/60 backdrop-blur-sm hover:border-primary/40 transition-colors">
                                <CardContent className="p-5 space-y-3">
                                    <div className="flex items-center justify-between">
                                        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                                            <item.icon size={18} />
                                        </div>
                                        <Badge variant="outline" className="text-[10px] font-mono">
                                            {item.badge}
                                        </Badge>
                                    </div>
                                    <div className="space-y-1">
                                        <h3 className="font-semibold text-sm text-foreground">{item.title}</h3>
                                        <p className="text-xs text-muted-foreground leading-relaxed">
                                            {item.description}
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                </div>

                {/* Quick Actions Footer */}
                {strategy && (
                    <div className="p-4 rounded-xl border border-border/80 bg-muted/30 flex flex-col sm:flex-row items-center justify-between gap-4">
                        <div className="text-xs text-muted-foreground text-center sm:text-left">
                            {t("liveTradingRoadmap.currentStrategy", { name: strategy.name })}
                        </div>
                        <div className="flex items-center gap-3 w-full sm:w-auto justify-center">
                            <Button
                                variant="outline"
                                size="sm"
                                className="gap-2 text-xs"
                                onClick={() => navigate(`/strategy/${strategy.id}/code`)}
                            >
                                <Code size={14} />
                                <span>{t("liveTradingRoadmap.viewCode")}</span>
                            </Button>
                            <Button
                                size="sm"
                                className="gap-2 text-xs"
                                onClick={() => navigate(`/strategy/${strategy.id}/backtest`)}
                            >
                                <LineChart size={14} />
                                <span>{t("liveTradingRoadmap.goToBacktest")}</span>
                                <ArrowRight size={13} />
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default LiveTradingView;
