import { Logo } from "@/components/Logo";
import { useTranslation } from "react-i18next";

const Footer = () => {
    const { t } = useTranslation();

    const columns = [
        {
            heading: t("landing.footer.product"),
            links: [
                { label: t("landing.nav.features"), href: "#features" },
                { label: t("landing.nav.pricing"), href: "#pricing" },
                { label: t("landing.footer.documentation"), href: "#docs" },
                { label: t("landing.footer.apiReference"), href: "#docs" },
            ],
        },
        {
            heading: t("landing.footer.company"),
            links: [
                { label: t("landing.footer.about"), href: "#" },
                { label: t("landing.footer.blog"), href: "#" },
                { label: t("landing.footer.careers"), href: "#" },
                { label: t("landing.footer.contact"), href: "#" },
            ],
        },
        {
            heading: t("landing.footer.followUs"),
            links: [
                { label: t("landing.footer.twitter"), href: "#" },
                { label: t("landing.footer.discord"), href: "#" },
                { label: t("landing.footer.github"), href: "#" },
            ],
        },
    ];

    return (
        <footer className="border-t border-border bg-background py-14">
            <div className="container">
                <div className="grid gap-10 md:grid-cols-[1.4fr_repeat(3,1fr)]">
                    <div>
                        <Logo size="sm" />
                        <p className="mt-4 max-w-[44ch] text-sm leading-relaxed text-muted-foreground">
                            {t("landing.footer.description")}
                        </p>
                    </div>

                    {columns.map((column) => (
                        <div key={column.heading}>
                            <h3 className="text-sm font-semibold text-foreground">{column.heading}</h3>
                            <ul className="mt-4 space-y-2.5">
                                {column.links.map((link) => (
                                    <li key={link.label}>
                                        <a
                                            href={link.href}
                                            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                                        >
                                            {link.label}
                                        </a>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}
                </div>

                <div className="mt-12 flex flex-col gap-3 border-t border-border pt-6 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm text-muted-foreground">{t("landing.footer.copyright")}</p>
                    <div className="flex gap-5">
                        <a href="#" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
                            {t("landing.footer.privacy")}
                        </a>
                        <a href="#" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
                            {t("landing.footer.terms")}
                        </a>
                    </div>
                </div>
            </div>
        </footer>
    );
};

export default Footer;
