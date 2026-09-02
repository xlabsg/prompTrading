import { Code, LineChart, Zap, Shield, Brain, RefreshCw } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

/**
 * A lattice, not a card deck: the cells share hairlines so the six capabilities
 * read as one instrument panel instead of six things competing for a click.
 */
const Features = () => {
    const { t } = useTranslation();
    const features = useMemo(
        () => [
            { icon: Brain, title: t("landing.features.items.aiTitle"), description: t("landing.features.items.aiDesc") },
            { icon: Code, title: t("landing.features.items.codeTitle"), description: t("landing.features.items.codeDesc") },
            { icon: LineChart, title: t("landing.features.items.backtestTitle"), description: t("landing.features.items.backtestDesc") },
            { icon: Zap, title: t("landing.features.items.liveTitle"), description: t("landing.features.items.liveDesc") },
            { icon: RefreshCw, title: t("landing.features.items.refineTitle"), description: t("landing.features.items.refineDesc") },
            { icon: Shield, title: t("landing.features.items.riskTitle"), description: t("landing.features.items.riskDesc") },
        ],
        [t],
    );

    return (
        <section id="features" className="py-20 lg:py-28">
            <div className="container">
                <div className="max-w-2xl">
                    <h2 className="max-w-[15em] text-display font-semibold text-foreground">
                        {t("landing.features.title")}
                    </h2>
                    <p className="mt-4 max-w-[52ch] text-lg leading-relaxed text-muted-foreground">
                        {t("landing.features.subtitle")}
                    </p>
                </div>

                <div className="mt-12 grid border-l border-t border-border sm:grid-cols-2 lg:grid-cols-3">
                    {features.map((feature) => (
                        <div key={feature.title} className="border-b border-r border-border bg-card p-6 lg:p-7">
                            <feature.icon className="h-5 w-5 text-foreground" strokeWidth={1.75} aria-hidden />
                            <h3 className="mt-4 text-[15px] font-semibold text-foreground">{feature.title}</h3>
                            <p className="mt-2 max-w-[42ch] text-sm leading-relaxed text-muted-foreground">
                                {feature.description}
                            </p>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
};

export default Features;
