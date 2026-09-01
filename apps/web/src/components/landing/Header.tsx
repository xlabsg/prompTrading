import { motion } from "framer-motion";
import { Menu, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/Logo";
import { LanguageSwitcher } from "@/components/common/LanguageSwitcher";

interface HeaderProps {
    onOpenAuth?: (step?: "login" | "register") => void;
}

const Header = ({ onOpenAuth }: HeaderProps) => {
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const { t } = useTranslation();

    return (
        <motion.header
            initial={{ y: -100 }}
            animate={{ y: 0 }}
            transition={{ duration: 0.5 }}
            className="fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-lg border-b border-border/50"
        >
            <div className="container mx-auto px-6">
                <div className="flex items-center justify-between h-16">
                    {/* Logo */}
                    <Logo size="sm" />

                    {/* Desktop Navigation */}
                    <nav className="hidden md:flex items-center gap-8">
                        <a
                            href="#features"
                            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                        >
                            {t("landing.nav.features")}
                        </a>
                        <a
                            href="#how-it-works"
                            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                        >
                            {t("landing.nav.howItWorks")}
                        </a>
                        <a
                            href="#pricing"
                            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                        >
                            {t("landing.nav.pricing")}
                        </a>
                        <a
                            href="#docs"
                            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                        >
                            {t("landing.nav.docs")}
                        </a>
                    </nav>

                    {/* Log in / Sign up Buttons */}
                    <div className="hidden md:flex items-center gap-3">
                        <LanguageSwitcher />
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onOpenAuth?.("login")}
                        >
                            {t("common.logIn")}
                        </Button>
                        <Button
                            size="sm"
                            onClick={() => onOpenAuth?.("register")}
                        >
                            {t("common.signUp")}
                        </Button>
                    </div>

                    {/* Mobile Menu Button */}
                    <button
                        onClick={() => setIsMenuOpen(!isMenuOpen)}
                        className="md:hidden p-2 text-foreground"
                    >
                        {isMenuOpen ? <X size={24} /> : <Menu size={24} />}
                    </button>
                </div>

                {/* Mobile Menu */}
                {isMenuOpen && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        className="md:hidden py-4 border-t border-border"
                    >
                        <nav className="flex flex-col gap-4">
                            <a
                                href="#features"
                                className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                            >
                                {t("landing.nav.features")}
                            </a>
                            <a
                                href="#how-it-works"
                                className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                            >
                                {t("landing.nav.howItWorks")}
                            </a>
                            <a
                                href="#pricing"
                                className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                            >
                                {t("landing.nav.pricing")}
                            </a>
                            <a
                                href="#docs"
                                className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                            >
                                {t("landing.nav.docs")}
                            </a>
                            <div className="pt-2">
                                <LanguageSwitcher />
                            </div>
                            <div className="flex flex-col gap-2 pt-4 border-t border-border">
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="w-full"
                                    onClick={() => {
                                        onOpenAuth?.("login");
                                        setIsMenuOpen(false);
                                    }}
                                >
                                    {t("common.logIn")}
                                </Button>
                                <Button
                                    size="sm"
                                    className="w-full"
                                    onClick={() => {
                                        onOpenAuth?.("register");
                                        setIsMenuOpen(false);
                                    }}
                                >
                                    {t("common.signUp")}
                                </Button>
                            </div>
                        </nav>
                    </motion.div>
                )}
            </div>
        </motion.header>
    );
};

export default Header;
