import { useMemo } from "react";
import { useTranslation } from "react-i18next";

/**
 * The only numbered thing on the site, because this content genuinely is a
 * sequence. The numbers sit on a rule that runs through the steps, so the rule
 * carries the ordering rather than four repeated badges.
 */
const HowItWorks = () => {
    const { t } = useTranslation();
    const steps = useMemo(
        () => [
            { number: "01", title: t("landing.howItWorks.steps.step1Title"), description: t("landing.howItWorks.steps.step1Desc") },
            { number: "02", title: t("landing.howItWorks.steps.step2Title"), description: t("landing.howItWorks.steps.step2Desc") },
            { number: "03", title: t("landing.howItWorks.steps.step3Title"), description: t("landing.howItWorks.steps.step3Desc") },
            { number: "04", title: t("landing.howItWorks.steps.step4Title"), description: t("landing.howItWorks.steps.step4Desc") },
        ],
        [t],
    );

    return (
        <section id="how-it-works" className="border-t border-border bg-card py-20 lg:py-28">
            <div className="container">
                <div className="max-w-2xl">
                    <h2 className="max-w-[15em] text-display font-semibold text-foreground">
                        {t("landing.howItWorks.title")}
                    </h2>
                    <p className="mt-4 max-w-[52ch] text-lg leading-relaxed text-muted-foreground">
                        {t("landing.howItWorks.subtitle")}
                    </p>
                </div>

                <ol className="relative mt-14 grid gap-10 lg:grid-cols-4 lg:gap-8">
                    {/* The rule the sequence runs along. */}
                    <div className="absolute left-[7px] top-2 hidden h-full w-px bg-border sm:block lg:left-0 lg:top-[7px] lg:h-px lg:w-full" aria-hidden />

                    {steps.map((step) => (
                        <li key={step.number} className="relative sm:pl-8 lg:pl-0 lg:pt-8">
                            <span
                                className="absolute left-0 top-1.5 hidden h-3.5 w-3.5 rounded-full border-2 border-primary bg-card sm:block lg:top-0"
                                aria-hidden
                            />
                            <span className="numeric text-sm text-muted-foreground">
                                {t("landing.howItWorks.stepLabel", { number: step.number })}
                            </span>
                            <h3 className="mt-2 text-[17px] font-semibold text-foreground">{step.title}</h3>
                            <p className="mt-2 max-w-[42ch] text-sm leading-relaxed text-muted-foreground">
                                {step.description}
                            </p>
                        </li>
                    ))}
                </ol>
            </div>
        </section>
    );
};

export default HowItWorks;
