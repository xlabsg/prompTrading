import { motion } from "framer-motion";
import { MessageSquare, Code, LineChart, Rocket } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

const HowItWorks = () => {
    const { t } = useTranslation();
    const steps = useMemo(
        () => [
            {
                number: "01",
                icon: MessageSquare,
                title: t("landing.howItWorks.steps.step1Title"),
                description: t("landing.howItWorks.steps.step1Desc"),
            },
            {
                number: "02",
                icon: Code,
                title: t("landing.howItWorks.steps.step2Title"),
                description: t("landing.howItWorks.steps.step2Desc"),
            },
            {
                number: "03",
                icon: LineChart,
                title: t("landing.howItWorks.steps.step3Title"),
                description: t("landing.howItWorks.steps.step3Desc"),
            },
            {
                number: "04",
                icon: Rocket,
                title: t("landing.howItWorks.steps.step4Title"),
                description: t("landing.howItWorks.steps.step4Desc"),
            },
        ],
        [t],
    );
    return (
        <section id="how-it-works" className="py-24">
            <div className="container mx-auto px-6">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                    viewport={{ once: true }}
                    className="text-center mb-16"
                >
                    <h2 className="font-display text-4xl sm:text-5xl font-bold text-foreground mb-4">
                        {t("landing.howItWorks.title")}
                    </h2>
                    <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                        {t("landing.howItWorks.subtitle")}
                    </p>
                </motion.div>

                <div className="relative">
                    {/* Connection Line */}
                    <div className="hidden lg:block absolute top-1/2 left-0 right-0 h-0.5 bg-gradient-to-r from-primary/20 via-primary to-primary/20 -translate-y-1/2" />

                    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
                        {steps.map((step, index) => (
                            <motion.div
                                key={index}
                                initial={{ opacity: 0, y: 30 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                transition={{ duration: 0.5, delay: index * 0.15 }}
                                viewport={{ once: true }}
                                className="relative"
                            >
                                <div className="flex flex-col items-center text-center">
                                    {/* Number Circle */}
                                    <div className="relative z-10 w-20 h-20 rounded-full bg-primary flex items-center justify-center mb-6 shadow-glow">
                                        <step.icon className="w-8 h-8 text-primary-foreground" />
                                    </div>

                                    {/* Step Number */}
                                    <span className="text-sm font-semibold text-primary mb-2">
                                        {t("landing.howItWorks.stepLabel", { number: step.number })}
                                    </span>

                                    <h3 className="text-xl font-semibold text-foreground mb-3">
                                        {step.title}
                                    </h3>
                                    <p className="text-muted-foreground">{step.description}</p>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
};

export default HowItWorks;
