import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

const CTA = () => {
    const { t } = useTranslation();

    return (
        <section className="ink-panel relative overflow-hidden">
            <div className="grid-rule absolute inset-0 opacity-60" aria-hidden />

            <div className="container relative py-20 lg:py-28">
                <div className="max-w-2xl">
                    <h2 className="max-w-[15em] text-display font-semibold text-ink-foreground">
                        {t("landing.cta.titleLine1")} {t("landing.cta.titleLine2")}
                    </h2>
                    <p className="mt-5 max-w-[52ch] text-lg leading-relaxed text-ink-muted">
                        {t("landing.cta.subtitle")}
                    </p>

                    <div className="mt-9 flex flex-wrap items-center gap-3">
                        <Button size="lg" className="group" asChild>
                            <Link to="/console">
                                {t("landing.cta.primaryCta")}
                                <ArrowRight className="transition-transform group-hover:translate-x-0.5" />
                            </Link>
                        </Button>
                        <Button
                            variant="ghost"
                            size="lg"
                            className="text-ink-muted hover:bg-ink-raised hover:text-ink-foreground"
                        >
                            {t("landing.cta.secondaryCta")}
                        </Button>
                    </div>

                    <p className="mt-6 text-sm text-ink-muted">{t("landing.cta.disclaimer")}</p>
                </div>
            </div>
        </section>
    );
};

export default CTA;
