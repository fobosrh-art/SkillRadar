import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Briefcase, Building2, Database, Layers, ShieldCheck, Sparkles, Wallet } from "lucide-react";
import { useApi } from "../lib/api";
import { Overview as OverviewT } from "../lib/types";
import { date, int, langName, pct, salary, share, shortDay, skillType } from "../lib/format";
import { Card, Empty, ErrorBox, Loading, Note, PageHeader, Segmented, Stat, StatusBadge, TableWrap } from "../components/ui";
import { Columns, RankBars, SegmentBar } from "../components/charts";
import { VacancyDrawer } from "../components/VacancyDrawer";
import { useEscoLabels } from "../lib/labels";


export default function Overview() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useApi<OverviewT>("/api/overview");
  const [job, setJob] = useState<string | null>(null);
  const [basis, setBasis] = useState<"posted" | "first_seen">("posted");
  const nav = useNavigate();
  const { tl } = useEscoLabels();
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data?.published) return <Empty title={t("overview.noData")} icon={<Database size={28} />}>{t("overview.noDataHint")}</Empty>;

  const k = data.kpis;
  const pub = data.publication;
  const postedDays = data.posted_trend.length;
  const postedMissing = k.vacancies - data.posted_trend.reduce((s, d) => s + d.vacancies, 0);
  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("overview.eyebrow")} title={t("overview.title")}
        description={t("overview.desc", { v: pub.version, n: int(k.vacancies), s: k.sources })}
        actions={<Link to="/jobs" className="btn-primary">{t("overview.explore")} <ArrowRight size={15} /></Link>} />

      <div className="card p-5">
        <div className="text-sm font-semibold text-ink">{t("overview.howTitle")}</div>
        <ol className="mt-3 grid gap-3 md:grid-cols-3">
          {[["1", "how1", "/jobs"], ["2", "how2", "/career"], ["3", "how3", "/roadmap"]].map(([n, k, to]) => (
            <li key={k} className="flex gap-3 rounded-lg bg-slate-50 p-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold text-white">{n}</span>
              <div className="text-sm leading-6 text-ink-soft">{t(`overview.${k}`)} <Link to={to} className="font-medium text-indigo-700">{t(`overview.${k}Link`)} →</Link></div>
            </li>
          ))}
        </ol>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label={t("overview.kVac")} value={int(k.vacancies)} icon={<Briefcase size={16} />}
          sub={t("overview.kVacSub", { raw: int(k.raw_records), dup: int(k.duplicates_removed) })} />
        <Stat label={t("overview.kEmp")} value={int(k.employers)} icon={<Building2 size={16} />} sub={t("overview.kEmpSub")} />
        <Stat label={t("overview.kSrc")} value={int(k.sources)} icon={<Layers size={16} />} sub={t("overview.kSrcSub")} />
        <Stat label={t("overview.kSkills")} value={int(k.distinct_skills)} icon={<Sparkles size={16} />}
          sub={t("overview.kSkillsSub", { m: int(k.skill_matches), v: int(k.with_skills) })} />
        <Stat label={t("overview.kSalary")} value={pct(share(k.with_salary, k.vacancies))} icon={<Wallet size={16} />}
          sub={t("overview.kSalarySub", { n: int(k.with_salary), t: int(k.vacancies) })} />
        <Stat label={t("overview.kQuality")} value={`${data.quality.passed}/${data.quality.total}`} icon={<ShieldCheck size={16} />}
          tone={data.quality.passed === data.quality.total ? "good" : "bad"}
          sub={data.last_run ? <span className="inline-flex flex-wrap items-center gap-1.5">{t("overview.lastRun")} <StatusBadge status={data.last_run.status} /></span> : null} />
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3" title={t("overview.topSkills")} subtitle={t("overview.topSkillsSub")}
          actions={<Link to="/skills" className="btn-ghost text-xs">{t("overview.allSkills")} <ArrowRight size={14} /></Link>}>
          <RankBars data={data.top_skills.map((s) => ({ ...s, en: s.skill_label, skill_label: tl("skill", s.skill_uri, s.skill_label) }))} label="skill_label" value="share_of_text_pct" valueSuffix="%"
            onClick={(d) => nav(`/skills?skill=${encodeURIComponent(d.skill_uri)}`)}
            tooltip={(d) => [d.skill_label, [[t("common.vacancy"), int(d.vacancies)], [t("overview.share"), pct(d.share_of_text_pct)], [t("overview.esco"), skillType(d.skill_type)], ["ESCO (EN)", d.en]]]} />
        </Card>
        <Card className="xl:col-span-2" title={t("overview.bySource")} subtitle={t("overview.bySourceSub")}>
          <RankBars data={data.sources} label="source_name" value="vacancies" maxLabel={18}
            tooltip={(d) => [d.source_name, [[t("common.vacancy"), int(d.vacancies)], [t("overview.share"), pct(d.share_pct)], [t("overview.withSalary"), int(d.with_salary)], [t("overview.withText"), int(d.with_text)]]]} />
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3" title={t("overview.timeline")}
          subtitle={basis === "posted" ? t("overview.timelinePosted") : t("overview.timelineSeen")}
          actions={<Segmented value={basis} onChange={setBasis} options={[{ value: "posted", label: t("overview.postedDate") }, { value: "first_seen", label: t("overview.firstSeen") }]} />}>
          <Columns data={basis === "posted" ? data.posted_trend : data.first_seen_trend} x="day" y="vacancies" xFormat={shortDay} height={230}
            tooltip={(d) => [shortDay(d.day as string), [[basis === "posted" ? t("overview.vacPosted") : t("overview.vacSeen"), int(d.vacancies as number)]]]} />
          <p className="mt-2 text-xs text-ink-muted">{t("overview.timelineNote", { days: postedDays, missing: int(postedMissing) })}</p>
        </Card>
        <Card className="xl:col-span-2" title={t("overview.coverage")} subtitle={t("overview.coverageSub")}>
          <SegmentBar parts={[
            { label: t("overview.found"), value: k.with_skills },
            { label: t("overview.noMatch"), value: k.no_match },
            { label: t("overview.noText"), value: k.no_text, hint: t("overview.unknown") },
          ]} />
          <div className="mt-5 border-t border-slate-100 pt-4">
            <div className="mb-2 text-xs font-medium text-ink-muted">{t("overview.textLang")}</div>
            <div className="flex flex-wrap gap-2">
              {data.languages.map((l) => (
                <span key={l.lang} className="chip bg-slate-100 text-ink-soft">{langName(l.lang)} <span className="tabular text-ink-muted">{int(l.n)}</span></span>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2" title={t("overview.latest")} bodyClass="p-0"
          actions={<Link to="/jobs" className="btn-ghost text-xs">{t("overview.explorer")} <ArrowRight size={14} /></Link>}>
          <TableWrap>
            <table className="w-full min-w-[640px]">
              <thead className="border-b border-slate-100"><tr>
                <th className="th pl-5">{t("overview.colVacancy")}</th><th className="th">{t("common.source")}</th><th className="th">{t("overview.colSalary")}</th><th className="th">{t("overview.colSkills")}</th><th className="th">{t("common.posted")}</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.recent.map((r) => (
                  <tr key={r.job_id} className="cursor-pointer hover:bg-slate-50" onClick={() => setJob(r.job_id)}>
                    <td className="td pl-5"><div className="font-medium text-ink">{r.title}</div><div className="text-xs text-ink-muted">{r.company_name ?? t("common.employerNotStated")}</div></td>
                    <td className="td">{r.source_name}</td>
                    <td className="td tabular">{salary(r.salary_from, r.salary_to, r.salary_currency, r.salary_period)}</td>
                    <td className="td tabular">{int(r.skill_count)}</td>
                    <td className="td whitespace-nowrap">{date(r.posted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </Card>
        <div className="space-y-6">
          <Card title={t("overview.topOcc")} subtitle={t("overview.topOccSub", { n: int(k.with_occupation), t: int(k.vacancies) })}>
            <ul className="space-y-2.5">
              {data.occupations.map((o) => (
                <li key={o.occupation_uri} className="flex items-center justify-between gap-3 text-sm">
                  <Link to={`/skills?occupation=${encodeURIComponent(o.occupation_uri)}`} className="truncate text-ink-soft hover:text-indigo-700" title={`ESCO (EN): ${o.occupation_label}`}>{tl("occupation", o.occupation_uri, o.occupation_label)}</Link>
                  <span className="tabular text-ink-muted">{int(o.vacancies)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[11px] text-ink-faint">{t("common.localLabels")}</p>
          </Card>
          <Card title={t("overview.topEmp")}>
            <ul className="space-y-2.5">
              {data.companies.map((c) => (
                <li key={c.company_name} className="flex items-center justify-between gap-3 text-sm">
                  <span className="truncate text-ink-soft">{c.company_name}</span>
                  <span className="tabular text-ink-muted">{int(c.vacancies)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>

      <Note title={t("overview.limitsTitle")}>
        {t("overview.limits", { raw: int(k.raw_records) })} <Link className="font-medium underline" to="/sources">{t("overview.seeSources")}</Link>
        <div className="mt-1">{t("common.escoEnNote")}</div>
      </Note>
      <VacancyDrawer jobId={job} onClose={() => setJob(null)} />
    </div>
  );
}
