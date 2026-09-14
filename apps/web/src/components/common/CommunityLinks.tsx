// lucide-react 1.x ships no brand icons, so these are generic stand-ins.
import { GitFork, MessageCircle, Send, Bug } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

// Kept in sync with the Community section of the repository README.
export const GITHUB_URL = "https://github.com/xlabsg/prompTrading";
export const GITHUB_ISSUES_URL = "https://github.com/xlabsg/prompTrading/issues";
export const DISCORD_URL = "https://discord.gg/GNDx2rjCP";
export const TELEGRAM_URL = "https://t.me/+nzrCKig99880OTRl";

interface CommunityLinksProps {
    className?: string;
    /** Show the issue tracker alongside the three community destinations. */
    withIssues?: boolean;
}

/** Community destinations shown on the public-facing pages. */
export const CommunityLinks = ({ className, withIssues = false }: CommunityLinksProps) => {
    const { t } = useTranslation();

    const links = [
        { href: GITHUB_URL, icon: GitFork, label: t("landing.footer.github") },
        { href: DISCORD_URL, icon: MessageCircle, label: t("landing.footer.discord") },
        { href: TELEGRAM_URL, icon: Send, label: t("landing.footer.telegram") },
        ...(withIssues
            ? [{ href: GITHUB_ISSUES_URL, icon: Bug, label: t("landing.footer.issues") }]
            : []),
    ];

    return (
        <div className={cn("flex flex-wrap items-center justify-center gap-x-6 gap-y-2", className)}>
            {links.map(({ href, icon: Icon, label }) => (
                <a
                    key={href}
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                    <Icon size={15} />
                    {label}
                </a>
            ))}
        </div>
    );
};
