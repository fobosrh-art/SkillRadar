import i18n, { currentLocale } from "../i18n";

// All formatting follows the selected UI language and shows times in Baku local time.
export const TZ = "Asia/Baku";

const nf = (opts?: Intl.NumberFormatOptions) => new Intl.NumberFormat(currentLocale(), opts);

export const num = (v: number | null | undefined, digits = 0): string =>
  v === null || v === undefined ? "—" : nf({ maximumFractionDigits: digits }).format(v);

export const int = (v: number | null | undefined): string =>
  v === null || v === undefined ? "—" : nf({ maximumFractionDigits: 1 }).format(v);

/** v is already a percentage (0-100). */
export const pct = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined ? "—" : nf({ style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v / 100);

export const share = (part: number, whole: number): number => (whole ? (part / whole) * 100 : 0);

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export const date = (iso: string | null | undefined): string => {
  const d = parse(iso);
  return d ? d.toLocaleDateString(currentLocale(), { day: "numeric", month: "short", year: "numeric", timeZone: TZ }) : "—";
};

export const dateTime = (iso: string | null | undefined): string => {
  const d = parse(iso);
  return d
    ? d.toLocaleString(currentLocale(), { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: TZ })
    : "—";
};

/** Calendar day keys (YYYY-MM-DD) are dates, not instants: format them without a timezone shift. */
export const shortDay = (day: string): string => {
  const d = parse(`${day}T00:00:00Z`);
  return d ? d.toLocaleDateString(currentLocale(), { day: "numeric", month: "short", timeZone: "UTC" }) : day;
};

export function ago(iso: string | null | undefined): string {
  const d = parse(iso);
  if (!d) return "—";
  const s = (Date.now() - d.getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(currentLocale(), { numeric: "auto" });
  if (s < 60) return rtf.format(0, "second");
  if (s < 3600) return rtf.format(-Math.round(s / 60), "minute");
  if (s < 86400) return rtf.format(-Math.round(s / 3600), "hour");
  return rtf.format(-Math.round(s / 86400), "day");
}

export const hours = (h: number | null | undefined): string =>
  h === null || h === undefined ? "—" : h < 48 ? `${num(h, 1)} ${i18n.t("units.h")}` : `${num(h / 24, 1)} ${i18n.t("units.d")}`;

export const seconds = (s: number | null | undefined): string =>
  s === null || s === undefined ? "—" : s < 1 ? `${num(s * 1000)} ${i18n.t("units.ms")}` : `${num(s, 2)} ${i18n.t("units.s")}`;

export const periodLabel = (p: string | null | undefined): string =>
  !p || p === "unspecified" ? i18n.t("salary.periodUnspecified") : i18n.t(`salary.per.${p}`, { defaultValue: p.toLowerCase() });

/** Never invents a value: missing ends are shown as floor/ceiling only. */
export function salary(from: number | null, to: number | null, currency: string | null, period?: string | null): string {
  if (from === null && to === null) return i18n.t("salary.notPublished");
  const c = currency ?? "";
  const per = period ? ` / ${i18n.t(`salary.unit.${period}`, { defaultValue: period.toLowerCase() })}` : "";
  if (from !== null && to !== null) return from === to ? `${int(from)} ${c}${per}` : `${int(from)}–${int(to)} ${c}${per}`;
  if (from !== null) return i18n.t("salary.from", { v: `${int(from)} ${c}${per}` });
  return i18n.t("salary.upTo", { v: `${int(to)} ${c}${per}` });
}

export const employment = (v: string | null | undefined) => (v ? i18n.t(`employment.${v}`, { defaultValue: v }) : "—");
export const langName = (v: string | null | undefined) => i18n.t(`lang.${v ?? "unknown"}`, { defaultValue: v ?? "—" });
export const labelType = (v: string) => i18n.t(`labelType.${v}`, { defaultValue: v });
export const skillType = (v: string | null | undefined) => (v ? i18n.t(`skillType.${v}`, { defaultValue: v }) : "—");
