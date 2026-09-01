import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./resources/en";
import zh from "./resources/zh";

const STORAGE_KEY = "asp_language";
const supportedLanguages = ["en", "zh"] as const;

export type SupportedLanguage = (typeof supportedLanguages)[number];

const getStoredLanguage = (): SupportedLanguage | null => {
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "zh") return stored;
  return null;
};

const detectLanguage = (): SupportedLanguage => {
  const stored = getStoredLanguage();
  if (stored) return stored;
  if (typeof navigator !== "undefined") {
    const lang = navigator.language.toLowerCase();
    if (lang.startsWith("zh")) return "zh";
  }
  return "en";
};

const setDocumentLanguage = (lang: SupportedLanguage) => {
  if (typeof document === "undefined") return;
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
};

export const setLanguage = (lang: SupportedLanguage) => {
  i18n.changeLanguage(lang);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, lang);
  }
  setDocumentLanguage(lang);
};

const initialLanguage = detectLanguage();
const storedLanguage = getStoredLanguage();

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    zh: { translation: zh },
  },
  lng: initialLanguage,
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnEmptyString: false,
});

if (!storedLanguage && typeof window !== "undefined") {
  window.localStorage.setItem(STORAGE_KEY, initialLanguage);
}

setDocumentLanguage(initialLanguage);

export { i18n, supportedLanguages, STORAGE_KEY };
