import { ReactNode, useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Activity, BadgeDollarSign, BarChart3, Briefcase, Database, GitBranch, Languages, LayoutDashboard, Menu, Route, ShieldCheck,
  Target, Wrench, X,
} from "lucide-react";
import { useApi } from "../lib/api";
import { Health } from "../lib/types";
import { ago, dateTime, int } from "../lib/format";
import { LANGUAGES, Lang, setLanguage } from "../i18n";
import { cx } from "./ui";

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#4f46e5" />
      <circle cx="16" cy="16" r="9" fill="none" stroke="#c7d2fe" strokeWidth="2" />
      <circle cx="16" cy="16" r="4.5" fill="none" stroke="#e0e7ff" strokeWidth="2" />
      <path d="M16 16 L23.5 9.5" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="16" cy="16" r="2" fill="#fff" />
    </svg>
  );
}

const NAV: { group: string; items: { to: string; key: string; icon: ReactNode }[] }[] = [
  { group: "nav.market", items: [
    { to: "/", key: "nav.overview", icon: <LayoutDashboard size={17} /> },
    { to: "/jobs", key: "nav.jobs", icon: <Briefcase size={17} /> },
    { to: "/skills", key: "nav.skills", icon: <BarChart3 size={17} /> },
    { to: "/salary", key: "nav.salary", icon: <BadgeDollarSign size={17} /> },
  ] },
  { group: "nav.career", items: [
    { to: "/career", key: "nav.careerMatch", icon: <Target size={17} /> },
    { to: "/roadmap", key: "nav.roadmap", icon: <Route size={17} /> },
  ] },
  { group: "nav.platform", items: [
    { to: "/pipeline", key: "nav.pipeline", icon: <Activity size={17} /> },
    { to: "/quality", key: "nav.quality", icon: <ShieldCheck size={17} /> },
    { to: "/sources", key: "nav.sources", icon: <GitBranch size={17} /> },
    { to: "/operations", key: "nav.operations", icon: <Wrench size={17} /> },
  ] },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  return (
    <nav className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <Logo />
        <div className="min-w-0">
          <div className="text-[15px] font-semibold tracking-tight text-ink">SkillRadar</div>
          <div className="text-[11px] leading-4 text-ink-muted">{t("app.tagline")}</div>
        </div>
      </div>
      <div className="flex-1 space-y-6 overflow-y-auto px-3 pb-6">
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">{t(g.group)}</div>
            <ul className="space-y-0.5">
              {g.items.map((it) => (
                <li key={it.to}>
                  <NavLink to={it.to} end={it.to === "/"} onClick={onNavigate}
                    className={({ isActive }) => cx("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition",
                      isActive ? "bg-indigo-50 text-indigo-700" : "text-ink-soft hover:bg-slate-100 hover:text-ink")}>
                    <span className="shrink-0">{it.icon}</span><span className="truncate">{t(it.key)}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-slate-200 px-5 py-4 text-[11px] leading-5 text-ink-muted">
        {t("app.footer1")}
        <br />{t("app.footer2")}
      </div>
    </nav>
  );
}

function PublicationStatus() {
  const { t } = useTranslation();
  const { data } = useApi<Health>("/api/health", { pollMs: 30000 });
  if (!data) return <span className="hidden text-xs text-ink-faint sm:inline">{t("pub.checking")}</span>;
  if (data.status === "no_data") return <span className="chip bg-amber-50 text-amber-800">{t("pub.none")}</span>;
  return (
    <div className="flex min-w-0 items-center gap-2 text-xs text-ink-muted" title={t("pub.publishedAt", { at: dateTime(data.published_at) })}>
      <Database size={14} className="hidden shrink-0 text-indigo-600 sm:block" />
      <span className="hidden md:inline">{t("pub.label")}</span>
      <span className="chip shrink-0 bg-indigo-50 text-indigo-700">Gold v{data.gold_version}</span>
      <span className="hidden truncate tabular sm:inline">{t("pub.summary", { n: int(data.vacancies), ago: ago(data.published_at) })}</span>
    </div>
  );
}

/** Shown only in synthetic demo mode, so demo numbers are never mistaken for real analytics. */
function DemoBanner() {
  const { t } = useTranslation();
  const { data } = useApi<Health>("/api/health");
  if (!data?.demo) return null;
  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs font-medium text-amber-900 sm:px-6">
      {t("app.demoBanner")}
    </div>
  );
}

/** RU / AZ / EN switcher: changes language instantly and persists it in localStorage. */
function LanguageSelect() {
  const { t, i18n } = useTranslation();
  return (
    <div className="flex items-center gap-1.5" role="group" aria-label={t("app.language")}>
      <Languages size={15} className="hidden text-ink-faint sm:block" aria-hidden="true" />
      <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5">
        {LANGUAGES.map((l) => (
          <button key={l.code} onClick={() => setLanguage(l.code as Lang)} title={l.name} aria-pressed={i18n.language === l.code}
            className={cx("rounded-md px-2 py-1 text-xs font-semibold transition",
              i18n.language === l.code ? "bg-white text-indigo-700 shadow-sm" : "text-ink-muted hover:text-ink")}>
            {l.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  // Block body on purpose: modern Chrome's window.scrollTo() returns a Promise. An expression-bodied effect
  // would return it, React would later call it as the cleanup function ("destroy is not a function") and the
  // whole app would unmount on the next navigation - the "page needs a manual refresh" bug.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [loc.pathname]);
  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-slate-200 bg-white lg:block">
        <Sidebar />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/30" onClick={() => setOpen(false)} />
          <aside className="relative h-full w-72 bg-white shadow-xl">
            <button className="btn-ghost absolute right-2 top-4 px-2" onClick={() => setOpen(false)} aria-label={t("app.closeMenu")}><X size={18} /></button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <button className="btn-ghost px-2 lg:hidden" onClick={() => setOpen(true)} aria-label={t("app.openMenu")}><Menu size={18} /></button>
            <div className="flex items-center gap-2 lg:hidden"><Logo size={24} /><span className="hidden font-semibold sm:inline">SkillRadar</span></div>
          </div>
          <div className="flex min-w-0 items-center gap-3 sm:gap-4">
            <PublicationStatus />
            <LanguageSelect />
          </div>
        </header>
        <DemoBanner />
        <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
