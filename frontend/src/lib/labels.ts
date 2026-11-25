import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "./api";

/** Local RU/AZ display labels for ESCO concepts (SkillRadar's own translations, not official ESCO ones).
 *  Loaded once; the active UI language picks the label; English ESCO label is the fallback. */
export interface LabelsResponse {
  source: string;
  skill: Record<string, { ru: string; az: string }>;
  occupation: Record<string, { ru: string; az: string }>;
  coverage: Record<string, { translated: number; total: number }> & { unresolved: string[] };
}

let cache: LabelsResponse | null = null;
let pending: Promise<LabelsResponse> | null = null;
const listeners = new Set<(d: LabelsResponse) => void>();

function loadOnce() {
  if (cache || pending) return;
  pending = api.get<LabelsResponse>("/api/labels").then((d) => {
    cache = d;
    listeners.forEach((l) => l(d));
    return d;
  }).catch(() => {
    pending = null; // fall back to English labels; retry on next mount
    return null as unknown as LabelsResponse;
  });
}

export type EscoKind = "skill" | "occupation";

export function useEscoLabels() {
  const { i18n } = useTranslation();
  const [data, setData] = useState<LabelsResponse | null>(cache);
  useEffect(() => {
    if (cache) {
      setData(cache);
      return;
    }
    listeners.add(setData);
    loadOnce();
    return () => {
      listeners.delete(setData);
    };
  }, []);
  const lang = i18n.language as "ru" | "az" | "en";
  /** Display label in the active language; English ESCO label when no local translation exists. */
  const tl = (kind: EscoKind, uri: string | null | undefined, en: string | null | undefined): string => {
    if (!en) return "";
    if (lang === "en" || !uri || !data) return en;
    return data[kind][uri]?.[lang] ?? en;
  };
  /** True when the label shown differs from the official English one (used for the tooltip). */
  const translated = (kind: EscoKind, uri: string | null | undefined) => lang !== "en" && !!uri && !!data?.[kind][uri];
  return { tl, translated, coverage: data?.coverage ?? null, lang };
}
