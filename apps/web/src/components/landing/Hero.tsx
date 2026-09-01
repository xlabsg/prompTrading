import { motion } from "framer-motion";
import { ArrowRight, Play, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";

interface HeroProps {
    onOpenAuth?: () => void;
}

const Hero = ({ onOpenAuth }: HeroProps) => {
    const { t } = useTranslation();
    return (
        <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-gradient-hero pt-20">
            {/* Background Elements */}
            <div className="absolute inset-0 overflow-hidden">
                {/* Gradient Orbs */}
                <motion.div
                    animate={{ scale: [1, 1.2, 1], opacity: [0.3, 0.5, 0.3] }}
                    transition={{ duration: 8, repeat: Infinity }}
                    className="absolute top-1/4 -left-20 w-96 h-96 bg-primary/20 rounded-full blur-3xl"
                />
                <motion.div
                    animate={{ scale: [1.2, 1, 1.2], opacity: [0.2, 0.4, 0.2] }}
                    transition={{ duration: 10, repeat: Infinity }}
                    className="absolute bottom-1/4 -right-20 w-96 h-96 bg-primary/15 rounded-full blur-3xl"
                />

                {/* Grid Pattern */}
                <div className="absolute inset-0 bg-[linear-gradient(to_right,hsl(var(--border))_1px,transparent_1px),linear-gradient(to_bottom,hsl(var(--border))_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_50%,#000_40%,transparent_100%)] opacity-40" />
            </div>

            <div className="container relative z-10 px-6">
                <div className="max-w-5xl mx-auto text-center">
                    {/* Badge */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5 }}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-8"
                    >
                        <Sparkles className="w-4 h-4 text-primary" />
                        <span className="text-sm font-medium text-foreground">
                            {t("landing.hero.badge")}
                        </span>
                    </motion.div>

                    {/* Main Headline */}
                    <motion.h1
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6, delay: 0.1 }}
                        className="font-display text-5xl sm:text-6xl lg:text-7xl xl:text-8xl font-bold tracking-tight mb-6"
                    >
                        {t("landing.hero.headline")}
                        <br />
                        <span className="text-gradient-orange">{t("landing.hero.headlineAccent")}</span>
                    </motion.h1>

                    {/* Subtitle */}
                    <motion.p
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6, delay: 0.2 }}
                        className="text-lg sm:text-xl text-muted-foreground max-w-2xl mx-auto mb-10"
                    >
                        {t("landing.hero.subtitle")}
                    </motion.p>

                    {/* CTA Buttons */}
                    <motion.div
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6, delay: 0.3 }}
                        className="flex flex-col sm:flex-row items-center justify-center gap-4"
                    >
                        <Button
                            size="lg"
                            className="group text-base px-8 py-6 shadow-glow"
                            onClick={onOpenAuth}
                        >
                            {t("landing.hero.primaryCta")}
                            <ArrowRight className="ml-2 w-5 h-5 transition-transform group-hover:translate-x-1" />
                        </Button>
                        <Button
                            variant="ghost"
                            size="lg"
                            className="text-base px-8 py-6"
                        >
                            <Play className="mr-2 w-5 h-5" />
                            {t("landing.hero.secondaryCta")}
                        </Button>
                    </motion.div>

                    {/* Stats */}
                    <motion.div
                        initial={{ opacity: 0, y: 40 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6, delay: 0.5 }}
                        className="mt-20 grid grid-cols-2 lg:grid-cols-4 gap-8"
                    >
                        {[
                            { value: "10K+", label: t("landing.hero.stats.activeUsers") },
                            { value: "500M+", label: t("landing.hero.stats.tradesExecuted") },
                            { value: "99.9%", label: t("landing.hero.stats.uptime") },
                            { value: "2.5x", label: t("landing.hero.stats.avgReturns") },
                        ].map((stat, index) => (
                            <div key={index} className="text-center">
                                <div className="text-3xl lg:text-4xl font-display font-bold text-foreground mb-1">
                                    {stat.value}
                                </div>
                                <div className="text-sm text-muted-foreground">{stat.label}</div>
                            </div>
                        ))}
                    </motion.div>
                </div>
            </div>

            {/* Bottom Gradient Line */}
            <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-primary to-transparent" />
        </section>
    );
};

export default Hero;
