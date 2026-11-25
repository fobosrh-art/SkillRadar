import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { en } from "./en";
import { ru } from "./ru";
import { az } from "./az";

export const LANGUAGES = [
  { code: "ru", label: "RU", name: "Русский", locale: "ru-RU" },
  { code: "az", label: "AZ", name: "Azərbaycanca", locale: "az-Latn-AZ" },
  { code: "en", label: "EN", name: "English", locale: "en-GB" },
] as const;
export type Lang = (typeof LANGUAGES)[number]["code"];

const STORAGE_KEY = "skillradar.lang";
const DEFAULT: Lang = "ru";

function initial(): Lang {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v && LANGUAGES.some((l) => l.code === v)) return v as Lang;
  } catch {
    /* storage blocked: fall back to the default */
  }
  return DEFAULT;
}

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ru: { translation: ru }, az: { translation: az } },
  lng: initial(),
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React already escapes
  returnNull: false,
});

document.documentElement.lang = i18n.language;

export function setLanguage(code: Lang) {
  i18n.changeLanguage(code);
  document.documentElement.lang = code;
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* ignore */
  }
}

export function currentLocale(): string {
  return LANGUAGES.find((l) => l.code === i18n.language)?.locale ?? "ru-RU";
}

export default i18n;
