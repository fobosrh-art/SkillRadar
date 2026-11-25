import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Building2, CalendarDays, Info, RotateCcw, Search, SlidersHorizontal, Sparkles, Wallet, X } from "lucide-react";
import { qs, useApi, useDebounced } from "../lib/api";
import { Facets, VacancyPage } from "../lib/types";
import { date, employment, int, periodLabel, salary } from "../lib/format";
import { useEscoLabels } from "../lib/labels";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, Pagination, Select } from "../components/ui";
import { VacancyDrawer } from "../components/VacancyDrawer";

const PAGE_SIZE = 15;
const FILTER_KEYS = ["q", "source", "occupation", "skill", "employment_type", "company", "posted_within",
  "has_salary", "salary_min", "salary_max", "salary_period", "has_skills"] as const;

export default function Jobs() {
  const { t } = useTranslation();
  const { tl } = useEscoLabels();
  const [sp, setSp] = useSearchParams();
  const get = (k: string) => sp.get(k) ?? "";
  const [q, setQ] = useState(get("q"));
  const [smin, setSmin] = useState(get("salary_min"));
  const [smax, setSmax] = useState(get("salary_max"));
  const dq = useDebounced(q, 300);
  const dmin = useDebounced(smin, 500);
  const dmax = useDebounced(smax, 500);
  const page = Number(get("page") || 1);
  const rangeInvalid = dmin !== "" && dmax !== "" && Number(dmin) > Number(dmax);

  /** Any filter change resets pagination to page 1 (filters apply to the whole published dataset). */
  const setMany = (changes: Record<string, string>, resetPage = true) => {
    const n = new URLSearchParams(sp);
    Object.entries(changes).forEach(([k, v]) => (v ? n.set(k, v) : n.delete(k)));
    if (resetPage) n.delete("page");
    setSp(n, { replace: true });
  };
  const set = (k: string, v: string, resetPage = true) => setMany({ [k]: v }, resetPage && k !== "page");
  useEffect(() => {
    if (dq !== get("q")) set("q", dq);
  }, [dq]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (rangeInvalid) return; // do not apply an impossible range
    if (dmin !== get("salary_min") || dmax !== get("salary_max")) setMany({ salary_min: dmin, salary_max: dmax });
  }, [dmin, dmax]); // eslint-disable-line react-hooks/exhaustive-deps

  const facets = useApi<Facets>("/api/vacancies/facets");
  const list = useApi<VacancyPage>(`/api/vacancies${qs({
    q: get("q"), source: get("source"), occupation: get("occupation"), skill: get("skill"),
    employment_type: get("employment_type"), company: get("company"), posted_within: get("posted_within"),
    has_salary: get("has_salary"), salary_min: get("salary_min"), salary_max: get("salary_max"),
    salary_period: get("salary_period"), has_skills: get("has_skills"),
    sort: get("sort") || "newest", page, page_size: PAGE_SIZE,
  })}`);
  const active = FILTER_KEYS.filter((k) => get(k));
  const f = facets.data;
  const resetAll = () => { setQ(""); setSmin(""); setSmax(""); setSp(new URLSearchParams(), { replace: true }); };
  const chipValue = (k: string) => {
    const v = get(k);
    if (k === "source") return f?.sources.find((s) => s.value === v)?.label ?? v;
    if (k === "occupation") return tl("occupation", v, f?.occupations.find((s) => s.value === v)?.label ?? v);
    if (k === "skill") return tl("skill", v, f?.skills.find((s) => s.value === v)?.label ?? v);
    if (k === "company") return f?.companies.find((s) => s.value === v)?.label ?? v;
    if (k === "employment_type") return employment(v);
    if (k === "posted_within") return t(`jobs.posted.${v}`);
    if (k === "salary_period") return periodLabel(v);
    if (k === "has_salary") return v === "true" ? t("jobs.salaryYes") : t("jobs.salaryNo");
    if (k === "has_skills") return v === "true" ? t("jobs.evidenceYes") : t("jobs.evidenceNo");
    return v;
  };
  const clearChip = (k: string) => {
    if (k === "q") setQ("");
    if (k === "salary_min") setSmin("");
    if (k === "salary_max") setSmax("");
    set(k, "");
  };
  const pr = f?.posted_range;

  return (
    <div>
      <PageHeader eyebrow={t("jobs.eyebrow")} title={t("jobs.title")} description={t("jobs.desc")} />

      <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <Card title={<span className="inline-flex items-center gap-2"><SlidersHorizontal size={15} />{t("jobs.filters")}</span>}
          actions={active.length > 0 && <button className="btn-ghost px-2 text-xs" onClick={resetAll}><RotateCcw size={13} />{t("jobs.reset")}</button>}
          className="h-fit">
          <div className="space-y-4">
            <label className="block">
              <span className="label">{t("jobs.keyword")}</span>
              <div className="relative">
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
                <input className="input pl-9" placeholder={t("jobs.keywordPh")} value={q} onChange={(e) => setQ(e.target.value)} />
              </div>
              <span className="mt-1 block text-[11px] text-ink-faint">{t("jobs.keywordHint")}</span>
            </label>
            <Select label={t("jobs.occupation")} value={get("occupation")} onChange={(v) => set("occupation", v)}>
              <option value="">{t("jobs.allOccupations")}</option>
              {f?.occupations.map((s) => <option key={s.value} value={s.value}>{tl("occupation", s.value, s.label)} ({int(s.n)})</option>)}
            </Select>
            <Select label={t("jobs.skill")} value={get("skill")} onChange={(v) => set("skill", v)}>
              <option value="">{t("jobs.anySkill")}</option>
              {f?.skills.map((s) => <option key={s.value} value={s.value}>{tl("skill", s.value, s.label)} ({int(s.n)})</option>)}
            </Select>
            <Select label={t("jobs.company")} value={get("company")} onChange={(v) => set("company", v)}>
              <option value="">{t("jobs.allCompanies")}</option>
              {f?.companies.map((s) => <option key={s.value} value={s.value}>{s.label} ({int(s.n)})</option>)}
            </Select>
            <Select label={t("common.source")} value={get("source")} onChange={(v) => set("source", v)}>
              <option value="">{t("jobs.allSources")}</option>
              {f?.sources.map((s) => <option key={s.value} value={s.value}>{s.label ?? s.value} ({int(s.n)})</option>)}
            </Select>
            <Select label={t("jobs.empType")} value={get("employment_type")} onChange={(v) => set("employment_type", v)}>
              <option value="">{t("jobs.anyType")}</option>
              {f?.employment_types.map((s) => <option key={s.value} value={s.value}>{employment(s.value)} ({int(s.n)})</option>)}
            </Select>
            <div>
              <Select label={t("jobs.postedLabel")} value={get("posted_within")} onChange={(v) => set("posted_within", v)}>
                <option value="">{t("jobs.posted.any")}</option>
                {["today", "3", "7", "30"].map((k) => <option key={k} value={k}>{t(`jobs.posted.${k}`)}</option>)}
              </Select>
              {pr && <span className="mt-1 block text-[11px] leading-4 text-ink-faint">{t("jobs.postedRange", { a: date(pr.min_date), b: date(pr.max_date), today: date(pr.today_baku), n: pr.without_date })}</span>}
            </div>

            <div className="rounded-lg border border-slate-200 p-3">
              <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-ink-muted"><Wallet size={13} />{t("jobs.salaryRange")}</div>
              <div className="grid grid-cols-2 gap-2">
                <input className="input" inputMode="numeric" type="number" min={0} placeholder={t("jobs.salaryMin")} value={smin} onChange={(e) => setSmin(e.target.value)} aria-label={t("jobs.salaryMin")} />
                <input className="input" inputMode="numeric" type="number" min={0} placeholder={t("jobs.salaryMax")} value={smax} onChange={(e) => setSmax(e.target.value)} aria-label={t("jobs.salaryMax")} />
              </div>
              {rangeInvalid && <p className="mt-1.5 text-xs text-rose-700">{t("jobs.salaryInvalid")}</p>}
              <p className="mt-1.5 flex gap-1 text-[11px] leading-4 text-ink-faint"><Info size={12} className="mt-0.5 shrink-0" />{t("jobs.salaryHint")}</p>
              <div className="mt-2 space-y-2">
                <Select value={get("salary_period")} onChange={(v) => set("salary_period", v)}>
                  <option value="">{t("jobs.periodAny")}</option>
                  {f?.salary_periods.map((p) => <option key={p.value} value={p.value}>{periodLabel(p.value)} ({int(p.n)})</option>)}
                </Select>
                <label className="flex items-center gap-2 text-sm text-ink-soft">
                  <input type="checkbox" checked={get("has_salary") === "true"} onChange={(e) => set("has_salary", e.target.checked ? "true" : "")} />
                  {t("jobs.hideNoSalary")}
                </label>
              </div>
            </div>

            <Select label={t("jobs.evidence")} value={get("has_skills")} onChange={(v) => set("has_skills", v)}>
              <option value="">{t("common.any")}</option><option value="true">{t("jobs.evidenceYes")}</option><option value="false">{t("jobs.evidenceNo")}</option>
            </Select>
            {active.length > 0 && <button className="btn-secondary w-full" onClick={resetAll}><RotateCcw size={14} />{t("jobs.resetAll")}</button>}
          </div>
        </Card>

        <div className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm text-ink-muted">
              {list.data ? <span className="font-semibold text-ink tabular">{t("jobs.matchOf", { n: int(list.data.total), t: int(list.data.published_total) })}</span> : t("jobs.searching")}
            </div>
            <Select value={get("sort") || "newest"} onChange={(v) => set("sort", v)} className="w-60">
              <option value="newest">{t("jobs.sortNewest")}</option><option value="oldest">{t("jobs.sortOldest")}</option>
              <option value="salary">{t("jobs.sortSalary")}</option><option value="salary_asc">{t("jobs.sortSalaryAsc")}</option>
              <option value="skills">{t("jobs.sortSkills")}</option>
            </Select>
          </div>
          {active.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {active.map((k) => (
                <button key={k} className="chip bg-indigo-50 text-indigo-700 hover:bg-indigo-100" onClick={() => clearChip(k)}>
                  {t(`jobs.chip.${k}`)}: {chipValue(k)} <X size={12} />
                </button>
              ))}
            </div>
          )}
          {list.error && <ErrorBox message={list.error} onRetry={list.reload} />}
          {list.loading && !list.data && <Loading />}
          {list.data && list.data.items.length === 0 && (
            <div className="card"><Empty title={t("jobs.noResults")} icon={<Search size={26} />}>
              {t("jobs.noResultsHint")}
              {active.length > 0 && <div className="mt-3"><button className="btn-secondary" onClick={resetAll}><RotateCcw size={14} />{t("jobs.resetAll")}</button></div>}
            </Empty></div>
          )}
          <div className={list.loading ? "opacity-60 transition" : "transition"}>
            <ul className="space-y-3">
              {list.data?.items.map((v) => (
                <li key={v.job_id}>
                  <button onClick={() => set("job", v.job_id, false)}
                    className="card block w-full p-4 text-left transition hover:border-indigo-300 hover:shadow-md">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <div className="break-words font-semibold text-ink">{v.title}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted">
                          <span className="inline-flex items-center gap-1.5"><Building2 size={14} />{v.company_name ?? t("common.employerNotStated")}</span>
                          <span className="inline-flex items-center gap-1.5"><CalendarDays size={14} />{date(v.posted_at)}</span>
                          <span>{v.source_name}</span>
                        </div>
                      </div>
                      <div className={`inline-flex shrink-0 flex-col items-start gap-0.5 text-sm font-medium tabular sm:items-end ${v.has_salary ? "text-ink" : "text-ink-faint"}`}>
                        <span className="inline-flex items-center gap-1.5"><Wallet size={14} />{salary(v.salary_from, v.salary_to, v.salary_currency, v.salary_period)}</span>
                        {v.has_salary && !v.salary_period ? <span className="text-[11px] font-normal text-ink-faint">{t("salary.periodUnspecified")}</span> : null}
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {v.occupation_label && <Badge tone="indigo" title={`ESCO (EN): ${v.occupation_label}`}>{tl("occupation", v.occupation_uri, v.occupation_label)}</Badge>}
                      {v.employment_type && <Badge>{employment(v.employment_type)}</Badge>}
                      <Badge tone={v.skill_count ? "emerald" : "slate"}>
                        <Sparkles size={12} />{v.skill_count ? t("jobs.skillsFound", { n: v.skill_count }) : v.has_text ? t("jobs.noSkill") : t("jobs.noText")}
                      </Badge>
                      {v.also_listed_on.length > 0 && <Badge title={t("jobs.alsoOnTitle")}>{t("jobs.alsoOn", { s: v.also_listed_on.map((m) => m.source).join(", ") })}</Badge>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          {list.data && list.data.total > 0 && (
            <div className="card px-4 py-3"><Pagination page={page} pageSize={PAGE_SIZE} total={list.data.total} onPage={(p) => set("page", String(p), false)} /></div>
          )}
        </div>
      </div>
      <VacancyDrawer jobId={get("job") || null} onClose={() => set("job", "", false)} />
    </div>
  );
}
