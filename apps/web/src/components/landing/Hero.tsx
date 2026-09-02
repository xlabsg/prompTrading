import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";

interface HeroProps {
    onOpenAuth?: () => void;
}

// Equity curve of the sample run shown in the result panel. Drawn by hand so the
// hero carries no charting dependency.
const EQUITY_PATH =
    "M0 74 L14 71 L28 76 L42 66 L56 69 L70 58 L84 62 L98 47 L112 52 L126 55 L140 41 L154 44 L168 33 L182 38 L196 26 L210 30 L224 19 L238 22 L252 12 L266 15 L280 6";

const prefersReducedMotion = () =>
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * The prompt line types itself out once on load. This is the product's whole
 * premise — a sentence becomes a strategy — so it is the one place on the site
 * that spends motion.
 */
const useTypedPrompt = (text: string) => {
    const [typed, setTyped] = useState(text);
    const timer = useRef<number>();

    useEffect(() => {
        if (prefersReducedMotion()) {
            setTyped(text);
            return;
        }
        setTyped("");
        let i = 0;
        timer.current = window.setInterval(() => {
            i += 1;
            setTyped(text.slice(0, i));
            if (i >= text.length && timer.current) window.clearInterval(timer.current);
        }, 28);
        return () => {
            if (timer.current) window.clearInterval(timer.current);
        };
    }, [text]);

    return typed;
};

const Hero = ({ onOpenAuth }: HeroProps) => {
    const { t } = useTranslation();
    const prompt = t("landing.hero.promptExample");
    const typed = useTypedPrompt(prompt);

    const metrics = [
        { label: t("landing.hero.panel.return"), value: "+142.6%", tone: "text-long" },
        { label: t("landing.hero.panel.sharpe"), value: "2.14", tone: "text-ink-foreground" },
        { label: t("landing.hero.panel.maxDrawdown"), value: "-8.3%", tone: "text-short" },
        { label: t("landing.hero.panel.trades"), value: "318", tone: "text-ink-foreground" },
    ];

    const stats = [
        { value: "10K+", label: t("landing.hero.stats.activeUsers") },
        { value: "500M+", label: t("landing.hero.stats.tradesExecuted") },
        { value: "99.9%", label: t("landing.hero.stats.uptime") },
        { value: "2.5x", label: t("landing.hero.stats.avgReturns") },
    ];

    return (
        <section className="pt-16">
            <div className="container grid items-center gap-14 py-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] lg:gap-20 lg:py-24">
                <div className="animate-settle">
                    <p className="mb-6 flex items-center gap-2 text-sm text-muted-foreground">
                        <span className="h-1.5 w-1.5 rounded-full bg-long" aria-hidden />
                        {t("landing.hero.badge")}
                    </p>

                    {/* Weight, not colour, separates the two lines. */}
                    <h1 className="text-display-lg">
                        <span className="block font-semibold text-foreground">
                            {t("landing.hero.headline")}
                        </span>
                        <span className="block font-normal text-muted-foreground">
                            {t("landing.hero.headlineAccent")}
                        </span>
                    </h1>

                    <p className="mt-7 max-w-[52ch] text-lg leading-relaxed text-muted-foreground">
                        {t("landing.hero.subtitle")}
                    </p>

                    <div className="mt-9 max-w-xl overflow-hidden rounded-md border border-border bg-card">
                        <div className="flex items-center justify-between border-b border-border px-3.5 py-2">
                            <span className="text-xs text-muted-foreground">
                                {t("landing.hero.promptLabel")}
                            </span>
                            <span className="numeric text-xs text-muted-foreground">BTC-USDT</span>
                        </div>
                        <p className="numeric px-3.5 py-4 text-sm leading-relaxed text-foreground">
                            {typed}
                            <span
                                className="ml-0.5 inline-block h-[1.05em] w-[0.5em] translate-y-[0.15em] bg-primary animate-blink"
                                aria-hidden
                            />
                        </p>
                    </div>

                    <div className="mt-7 flex flex-wrap items-center gap-3">
                        <Button size="lg" className="group" onClick={onOpenAuth}>
                            {t("landing.hero.primaryCta")}
                            <ArrowRight className="transition-transform group-hover:translate-x-0.5" />
                        </Button>
                        <Button variant="ghost" size="lg" onClick={onOpenAuth}>
                            {t("landing.hero.secondaryCta")}
                        </Button>
                    </div>
                </div>

                {/* What the prompt produces: a real run, on ink, reading like a fill report. */}
                <aside className="ink-panel animate-settle overflow-hidden rounded-md [animation-delay:180ms]">
                    <div className="flex items-stretch border-b border-ink-line text-xs">
                        <span className="border-r border-ink-line px-3.5 py-2.5 text-ink-foreground">
                            {t("landing.hero.panel.title")}
                        </span>
                        <span className="numeric px-3.5 py-2.5 text-ink-muted">1h</span>
                        <span className="numeric ml-auto border-l border-ink-line px-3.5 py-2.5 text-ink-muted">
                            2024–2026
                        </span>
                    </div>

                    <div className="grid-rule px-5 pb-2 pt-6">
                        <svg viewBox="0 0 280 80" className="h-24 w-full" role="img" aria-label={t("landing.hero.panel.chartAlt")}>
                            <path d={`${EQUITY_PATH} L280 80 L0 80 Z`} fill="hsl(var(--long) / 0.14)" />
                            <path
                                d={EQUITY_PATH}
                                fill="none"
                                stroke="hsl(var(--long))"
                                strokeWidth="1.75"
                                strokeLinejoin="round"
                                vectorEffect="non-scaling-stroke"
                            />
                        </svg>
                    </div>

                    <dl className="divide-y divide-ink-line border-t border-ink-line">
                        {metrics.map((metric) => (
                            <div key={metric.label} className="flex items-baseline justify-between px-5 py-3">
                                <dt className="text-sm text-ink-muted">{metric.label}</dt>
                                <dd className={`numeric text-[15px] font-medium ${metric.tone}`}>
                                    {metric.value}
                                </dd>
                            </div>
                        ))}
                    </dl>
                </aside>
            </div>

            <div className="border-y border-border bg-card">
                <dl className="container grid grid-cols-2 divide-border sm:divide-x lg:grid-cols-4">
                    {stats.map((stat) => (
                        <div key={stat.label} className="px-0 py-6 sm:px-6 sm:first:pl-0">
                            <dd className="numeric text-2xl font-medium text-foreground">{stat.value}</dd>
                            <dt className="mt-1 text-sm text-muted-foreground">{stat.label}</dt>
                        </div>
                    ))}
                </dl>
            </div>
        </section>
    );
};

export default Hero;
