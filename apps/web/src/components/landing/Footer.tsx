import { Logo } from "@/components/Logo";
import { useTranslation } from "react-i18next";

const Footer = () => {
    const { t } = useTranslation();
    return (
        <footer className="bg-card border-t border-border py-16">
            <div className="container mx-auto px-6">
                <div className="grid md:grid-cols-4 gap-12">
                    {/* Logo & Description */}
                    <div className="md:col-span-2">
                        <div className="mb-4">
                            <Logo size="sm" />
                        </div>
                        <p className="text-muted-foreground max-w-sm mb-6">
                            {t("landing.footer.description")}
                        </p>
                        <div className="flex gap-4">
                            <a
                                href="#"
                                className="text-muted-foreground hover:text-foreground transition-colors"
                            >
                                {t("landing.footer.twitter")}
                            </a>
                            <a
                                href="#"
                                className="text-muted-foreground hover:text-foreground transition-colors"
                            >
                                {t("landing.footer.discord")}
                            </a>
                            <a
                                href="#"
                                className="text-muted-foreground hover:text-foreground transition-colors"
                            >
                                {t("landing.footer.github")}
                            </a>
                        </div>
                    </div>

                    {/* Product Links */}
                    <div>
                        <h3 className="font-semibold text-foreground mb-4">{t("landing.footer.product")}</h3>
                        <ul className="space-y-3">
                            <li>
                                <a
                                    href="#features"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    {t("landing.nav.features")}
                                </a>
                            </li>
                            <li>
                                <a
                                    href="#pricing"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    {t("landing.nav.pricing")}
                                </a>
                            </li>
                            <li>
                                <a
                                    href="#"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    {t("landing.footer.documentation")}
                                </a>
                            </li>
                            <li>
                                <a
                                    href="#"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    {t("landing.footer.apiReference")}
                                </a>
                            </li>
                        </ul>
                    </div>

                    {/* Company Links */}
                    <div>
                        <h3 className="font-semibold text-foreground mb-4">{t("landing.footer.company")}</h3>
                        <ul className="space-y-3">
                            <li>
                                <a
                                    href="#"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    {t("landing.footer.about")}
                                </a>
                            </li>
                            <li>
                                <a
                                    href="#"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    {t("landing.footer.blog")}
                                </a>
                            </li>
                            <li>
                                <a
                                    href="#"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    {t("landing.footer.careers")}
                                </a>
                            </li>
                            <li>
                                <a
                                    href="#"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    {t("landing.footer.contact")}
                                </a>
                            </li>
                        </ul>
                    </div>
                </div>

                <div className="border-t border-border mt-12 pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
                    <p className="text-sm text-muted-foreground">
                        {t("landing.footer.copyright")}
                    </p>
                    <div className="flex gap-6 text-sm">
                        <a
                            href="#"
                            className="text-muted-foreground hover:text-foreground transition-colors"
                        >
                            {t("landing.footer.privacy")}
                        </a>
                        <a
                            href="#"
                            className="text-muted-foreground hover:text-foreground transition-colors"
                        >
                            {t("landing.footer.terms")}
                        </a>
                    </div>
                </div>
            </div>
        </footer>
    );
};

export default Footer;
