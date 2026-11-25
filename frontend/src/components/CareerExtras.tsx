import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Briefcase, ExternalLink, Scale } from "lucide-react";
import { api } from "../lib/api";
import { int, pct, periodLabel, salary } from "../lib/format";
import { useEscoLabels } from "../lib/labels";
import { Badge, Card, Empty, ErrorBox, Loading, Meter, Note } from "./ui";
import { OccupationPicker, Picked } from "./CareerPickers";
import { VacancyDrawer } from "./VacancyDrawer";

interface SkillRef { skill_uri: string; label: string }
interface JobMatch {
  job_id: string; title: string; company_name: string | null; source_name: string | null; url: string | null;
  posted_at: string | null; salary_from: number | null; salary_to: number | null; salary_currency: string | null;
  salary_period: string | null; required: number; matched: SkillRef[]; missing: SkillRef[]; coverage_pct: number;
}
interface JobsResponse { occupation_vacancies: number; scored: number; without_skills: number; user_skills: number; items: JobMatch[] }

/** Real published vacancies of the chosen occupation ranked by coverage of their extracted skills. */
export function MatchingJobs({ occupation, skills }: { occupation: Picked; skills: Picked[] }) {
  const { t } = useTranslation();
  const { tl } = useEscoLabels();
  const [data, setData] = useState<JobsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [job, setJob] = useState<string | null>(null);
  const key = skills.map((s) => s.uri).join("|");
  useEffect(() => {
    api.post<JobsResponse>("/api/career/jobs", { occupation_uri: occupation.uri, skill_uris: skills.map((s) => s.uri) })
      .then((d) => { setData(d); setErr(null); }).catch((e: Error) => setErr(e.message));
  }, [occupation.uri, key]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card title={<span className="inline-flex items-center gap-2"><Briefcase size={15} />{t("cx.jobsTitle")}</span>}
      subtitle={data ? t("cx.jobsSub", { n: data.scored, t: data.occupation_vacancies, w: data.without_skills }) : undefined}>
      {err && <ErrorBox message={err} />}
      {!data && !err && <Loading />}
      {data && skills.length === 0 && <Note>{t("cx.jobsNoSkills")}</Note>}
      {data && data.items.length === 0 && <Empty title={t("cx.jobsNone")} />}
      {data && skills.length > 0 && data.items.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {data.items.map((j) => (
            <li key={j.job_id} className="py-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <button className="text-left font-medium text-ink hover:text-indigo-700" onClick={() => setJob(j.job_id)}>{j.title}</button>
                  <div className="text-xs text-ink-muted">{j.company_name ?? t("common.employerNotStated")} · {j.source_name} · {salary(j.salary_from, j.salary_to, j.salary_currency, j.salary_period)}{j.salary_from !== null || j.salary_to !== null ? (j.salary_period ? "" : ` (${periodLabel(null)})`) : ""}</div>
                </div>
                <div className="w-full shrink-0 sm:w-44">
                  <div className="mb-1 flex justify-between gap-2 text-xs"><span className="font-semibold tabular text-ink">{pct(j.coverage_pct, 0)}</span><span className="text-ink-muted">{t("cx.ofSkills", { m: j.matched.length, n: j.required })}</span></div>
                  <Meter value={j.coverage_pct} />
                  {j.required < 3 && <div className="mt-1 text-[11px] text-amber-700">{t("cx.fewSkills")}</div>}
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {j.matched.map((s) => <Badge key={s.skill_uri} tone="emerald">✓ {tl("skill", s.skill_uri, s.label)}</Badge>)}
                {j.missing.map((s) => <Badge key={s.skill_uri} tone="amber">+ {tl("skill", s.skill_uri, s.label)}</Badge>)}
              </div>
              <div className="mt-2 flex gap-3 text-xs">
                <button className="font-medium text-indigo-700" onClick={() => setJob(j.job_id)}>{t("cx.details")}</button>
                {j.url && <a className="inline-flex items-center gap-1 font-medium text-indigo-700" href={j.url} target="_blank" rel="noopener noreferrer"><ExternalLink size={12} />{t("drawer.original")}</a>}
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs leading-5 text-ink-muted">{t("cx.jobsNote")}</p>
      <VacancyDrawer jobId={job} onClose={() => setJob(null)} />
    </Card>
  );
}

interface CompareOcc {
  occupation: { occupation_uri: string; preferred_label: string };
  vacancies: number; market_coverage: { matched: number; total: number; weighted_pct: number | null };
  top_skills: { skill_uri: string; label: string; vacancies: number; share_pct: number; user_has: boolean }[];
  missing: { skill_uri: string; label: string; vacancies: number }[];
  salary: { currency: string; period: string; vacancies: number; median_from: number | null; median_to: number | null }[];
}
interface CompareResponse { occupations: CompareOcc[]; common_skills: { skill_uri: string; label: string; a: number; b: number; user_has: boolean }[] }

/** Side-by-side comparison of the chosen occupation with a second one. */
export function CompareOccupations({ occupation, skills }: { occupation: Picked; skills: Picked[] }) {
  const { t } = useTranslation();
  const { tl } = useEscoLabels();
  const [other, setOther] = useState<Picked | null>(null);
  const [data, setData] = useState<CompareResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const key = skills.map((s) => s.uri).join("|");
  useEffect(() => {
    if (!other || other.uri === occupation.uri) { setData(null); return; }
    api.post<CompareResponse>("/api/career/compare", { occupation_uris: [occupation.uri, other.uri], skill_uris: skills.map((s) => s.uri) })
      .then((d) => { setData(d); setErr(null); }).catch((e: Error) => setErr(e.message));
  }, [occupation.uri, other?.uri, key]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card title={<span className="inline-flex items-center gap-2"><Scale size={15} />{t("cx.cmpTitle")}</span>} subtitle={t("cx.cmpSub")}>
      <div className="max-w-md"><OccupationPicker value={other} onChange={setOther} /></div>
      {err && <div className="mt-3"><ErrorBox message={err} /></div>}
      {data && (
        <>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {data.occupations.map((o) => (
              <div key={o.occupation.occupation_uri} className="min-w-0 rounded-xl border border-slate-200 p-4">
                <div className="font-semibold text-ink">{tl("occupation", o.occupation.occupation_uri, o.occupation.preferred_label)}</div>
                <div className="mt-1 text-xs text-ink-muted">{t("cx.sample", { n: int(o.vacancies) })}{o.vacancies < 5 ? ` · ${t("cx.small")}` : ""}</div>
                <div className="mt-3 text-xs text-ink-muted">{t("cx.coverage")}</div>
                <div className="text-2xl font-semibold tabular">{o.market_coverage.weighted_pct === null ? "—" : pct(o.market_coverage.weighted_pct, 0)}</div>
                <Meter value={o.market_coverage.weighted_pct ?? 0} className="mt-1" />
                <div className="mt-3 text-xs font-medium text-ink-muted">{t("cx.topSkills")}</div>
                <ul className="mt-1 space-y-0.5 text-sm">{o.top_skills.map((s) => <li key={s.skill_uri} className="flex justify-between gap-2"><span className={s.user_has ? "text-emerald-700" : "text-ink-soft"}>{s.user_has ? "✓ " : ""}{tl("skill", s.skill_uri, s.label)}</span><span className="tabular text-xs text-ink-muted">{pct(s.share_pct, 0)}</span></li>)}</ul>
                <div className="mt-3 text-xs font-medium text-ink-muted">{t("cx.missing")}</div>
                <div className="mt-1 flex flex-wrap gap-1">{o.missing.length ? o.missing.map((s) => <Badge key={s.skill_uri} tone="amber">{tl("skill", s.skill_uri, s.label)}</Badge>) : <span className="text-xs text-ink-muted">{t("common.none")}</span>}</div>
                <div className="mt-3 text-xs font-medium text-ink-muted">{t("cx.salary")}</div>
                {o.salary.length === 0 ? <div className="text-xs text-ink-muted">{t("cx.noSalary")}</div> : (
                  <ul className="mt-1 space-y-0.5 text-xs">{o.salary.map((g) => <li key={g.currency + g.period}>{g.currency} · {periodLabel(g.period)}: {t("cx.salaryLine", { f: int(g.median_from), to: int(g.median_to), n: g.vacancies })}{g.vacancies < 3 ? ` (${t("cx.small")})` : ""}</li>)}</ul>
                )}
              </div>
            ))}
          </div>
          <div className="mt-4">
            <div className="text-xs font-medium text-ink-muted">{t("cx.common")}</div>
            <div className="mt-1 flex flex-wrap gap-1">{data.common_skills.map((s) => <Badge key={s.skill_uri} tone={s.user_has ? "emerald" : "slate"}>{s.user_has ? "✓ " : ""}{tl("skill", s.skill_uri, s.label)} ({s.a} / {s.b})</Badge>)}</div>
          </div>
        </>
      )}
      <p className="mt-3 text-xs leading-5 text-ink-muted">{t("cx.cmpNote")}</p>
    </Card>
  );
}
