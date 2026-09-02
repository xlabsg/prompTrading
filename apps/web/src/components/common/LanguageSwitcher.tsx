import { Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { setLanguage, supportedLanguages, type SupportedLanguage } from "@/i18n";

const languageLabels: Record<SupportedLanguage, { short: string; label: string }> = {
  en: { short: "EN", label: "English" },
  zh: { short: "中文", label: "中文" },
};

interface LanguageSwitcherProps {
  /** Set when the switcher sits on an ink surface (nav rail, landing header). */
  onInk?: boolean;
}

export const LanguageSwitcher = ({ onInk = false }: LanguageSwitcherProps) => {
  const { i18n, t } = useTranslation();
  const current = (i18n.language?.startsWith("zh") ? "zh" : "en") as SupportedLanguage;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn("gap-1.5", onInk && "text-ink-muted hover:bg-ink-raised hover:text-ink-foreground")}
        >
          <Globe size={15} />
          <span className="text-xs font-medium">{languageLabels[current].short}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {supportedLanguages.map((lang) => (
          <DropdownMenuItem
            key={lang}
            onClick={() => setLanguage(lang)}
            className={lang === current ? "font-semibold" : undefined}
          >
            {t(lang === "zh" ? "common.chinese" : "common.english")}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
