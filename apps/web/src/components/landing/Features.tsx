import { motion } from "framer-motion";
import { Code, LineChart, Zap, Shield, Brain, RefreshCw } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

const Features = () => {
    const { t } = useTranslation();
    const features = useMemo(
        () => [
            {
                icon: Brain,
                title: t("landing.features.items.aiTitle"),
                description: t("landing.features.items.aiDesc"),
            },
            {
                icon: Code,
                title: t("landing.features.items.codeTitle"),
                description: t("landing.features.items.codeDesc"),
            },
            {
                icon: LineChart,
                title: t("landing.features.items.backtestTitle"),
                description: t("landing.features.items.backtestDesc"),
            },
            {
                icon: Zap,
                title: t("landing.features.items.liveTitle"),
                description: t("landing.features.items.liveDesc"),
            },
            {
                icon: RefreshCw,
                title: t("landing.features.items.refineTitle"),
                description: t("landing.features.items.refineDesc"),
            },
            {
                icon: Shield,
                title: t("landing.features.items.riskTitle"),
                description: t("landing.features.items.riskDesc"),
            },
        ],
        [t],
    );
    return (
        <section id="features" className="py-24 bg-muted/30">
            <div className="container mx-auto px-6">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                    viewport={{ once: true }}
                    className="text-center mb-16"
                >
                    <h2 className="font-display text-4xl sm:text-5xl font-bold text-foreground mb-4">
                        {t("landing.features.title")}
                    </h2>
                    <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                        {t("landing.features.subtitle")}
                    </p>
                </motion.div>

                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {features.map((feature, index) => (
                        <motion.div
                            key={index}
                            initial={{ opacity: 0, y: 30 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: index * 0.1 }}
                            viewport={{ once: true }}
                            className="group p-6 rounded-2xl bg-card border border-border hover:border-primary/30 hover:shadow-soft transition-all duration-300"
                        >
                            <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                                <feature.icon className="w-6 h-6 text-primary" />
                            </div>
                            <h3 className="text-xl font-semibold text-foreground mb-2">
                                {feature.title}
                            </h3>
                            <p className="text-muted-foreground">{feature.description}</p>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
};

export default Features;
