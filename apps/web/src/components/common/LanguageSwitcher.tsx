import { Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { setLanguage, supportedLanguages, type SupportedLanguage } from "@/i18n";

const languageLabels: Record<SupportedLanguage, { short: string; label: string }> = {
  en: { short: "EN", label: "English" },
  zh: { short: "中文", label: "中文" },
};

export const LanguageSwitcher = () => {
  const { i18n, t } = useTranslation();
  const current = (i18n.language?.startsWith("zh") ? "zh" : "en") as SupportedLanguage;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-2">
          <Globe size={16} />
          <span className="text-xs font-semibold">{languageLabels[current].short}</span>
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
