import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

const CTA = () => {
    const { t } = useTranslation();
    return (
        <section className="py-24 relative overflow-hidden">
            {/* Background */}
            <div className="absolute inset-0 bg-secondary" />
            <div className="absolute inset-0 bg-[linear-gradient(to_right,hsl(var(--secondary)/0.8)_1px,transparent_1px),linear-gradient(to_bottom,hsl(var(--secondary)/0.8)_1px,transparent_1px)] bg-[size:4rem_4rem] opacity-20" />

            <div className="container relative z-10 mx-auto px-6">
                <motion.div
                    initial={{ opacity: 0, y: 30 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6 }}
                    viewport={{ once: true }}
                    className="max-w-3xl mx-auto text-center"
                >
                    <h2 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold text-secondary-foreground mb-6">
                        {t("landing.cta.titleLine1")}
                        <br />
                        <span className="text-primary">{t("landing.cta.titleLine2")}</span>
                    </h2>
                    <p className="text-lg text-secondary-foreground/70 mb-10 max-w-xl mx-auto">
                        {t("landing.cta.subtitle")}
                    </p>

                    <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                        <Link to="/console">
                            <Button
                                size="lg"
                                className="group text-base px-8 py-6 bg-primary text-primary-foreground hover:bg-primary/90 shadow-glow"
                            >
                                {t("landing.cta.primaryCta")}
                                <ArrowRight className="ml-2 w-5 h-5 transition-transform group-hover:translate-x-1" />
                            </Button>
                        </Link>
                        <Button
                            variant="outline"
                            size="lg"
                            className="text-base px-8 py-6 border-secondary-foreground/20 text-secondary-foreground hover:bg-secondary-foreground/10"
                        >
                            {t("landing.cta.secondaryCta")}
                        </Button>
                    </div>

                    <p className="text-sm text-secondary-foreground/50 mt-6">
                        {t("landing.cta.disclaimer")}
                    </p>
                </motion.div>
            </div>
        </section>
    );
};

export default CTA;
