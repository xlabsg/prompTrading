import { Menu, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/Logo";
import { LanguageSwitcher } from "@/components/common/LanguageSwitcher";

interface HeaderProps {
    onOpenAuth?: (step?: "login" | "register") => void;
}

// Ink chrome, matching the app's rails: the marketing site and the console read
// as one surface rather than two products.
const Header = ({ onOpenAuth }: HeaderProps) => {
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const { t } = useTranslation();

    const links = [
        { href: "#features", label: t("landing.nav.features") },
        { href: "#how-it-works", label: t("landing.nav.howItWorks") },
        { href: "#pricing", label: t("landing.nav.pricing") },
        { href: "#docs", label: t("landing.nav.docs") },
    ];

    return (
        <header className="ink-panel fixed inset-x-0 top-0 z-50 border-b border-ink-line">
            <div className="container">
                <div className="flex h-16 items-center justify-between">
                    <Logo size="sm" onInk />

                    <nav className="hidden items-center gap-7 md:flex">
                        {links.map((link) => (
                            <a
                                key={link.href}
                                href={link.href}
                                className="text-sm text-ink-muted transition-colors hover:text-ink-foreground"
                            >
                                {link.label}
                            </a>
                        ))}
                    </nav>

                    <div className="hidden items-center gap-2 md:flex">
                        <LanguageSwitcher onInk />
                        <Button
                            variant="ghost"
                            size="sm"
                            className="text-ink-muted hover:bg-ink-raised hover:text-ink-foreground"
                            onClick={() => onOpenAuth?.("login")}
                        >
                            {t("common.logIn")}
                        </Button>
                        <Button size="sm" onClick={() => onOpenAuth?.("register")}>
                            {t("common.signUp")}
                        </Button>
                    </div>

                    <button
                        onClick={() => setIsMenuOpen(!isMenuOpen)}
                        className="rounded-md p-2 text-ink-foreground md:hidden"
                        aria-expanded={isMenuOpen}
                        aria-label={t("landing.nav.menu")}
                    >
                        {isMenuOpen ? <X size={20} /> : <Menu size={20} />}
                    </button>
                </div>

                {isMenuOpen && (
                    <nav className="flex flex-col gap-1 border-t border-ink-line py-3 md:hidden">
                        {links.map((link) => (
                            <a
                                key={link.href}
                                href={link.href}
                                onClick={() => setIsMenuOpen(false)}
                                className="rounded-md px-2 py-2 text-sm text-ink-muted transition-colors hover:bg-ink-raised hover:text-ink-foreground"
                            >
                                {link.label}
                            </a>
                        ))}
                        <div className="mt-2 flex items-center gap-2 border-t border-ink-line pt-3">
                            <LanguageSwitcher onInk />
                            <Button
                                variant="ghost"
                                size="sm"
                                className="flex-1 text-ink-muted hover:bg-ink-raised hover:text-ink-foreground"
                                onClick={() => {
                                    onOpenAuth?.("login");
                                    setIsMenuOpen(false);
                                }}
                            >
                                {t("common.logIn")}
                            </Button>
                            <Button
                                size="sm"
                                className="flex-1"
                                onClick={() => {
                                    onOpenAuth?.("register");
                                    setIsMenuOpen(false);
                                }}
                            >
                                {t("common.signUp")}
                            </Button>
                        </div>
                    </nav>
                )}
            </div>
        </header>
    );
};

export default Header;
