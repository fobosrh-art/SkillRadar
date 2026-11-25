import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Wallet } from "lucide-react";
import { qs, useApi } from "../lib/api";
import { SalaryBreakdown, SalaryResponse } from "../lib/types";
import { employment, int, pct, periodLabel } from "../lib/format";
import { Card, Empty, ErrorBox, Loading, Note, PageHeader, Stat, TableWrap, cx } from "../components/ui";
import { Columns, RankBars } from "../components/charts";
import { VacancyDrawer } from "../components/VacancyDrawer";
import { useEscoLabels } from "../lib/labels";


function BreakdownTable({ rows, cur, label }: { rows: SalaryBreakdown[]; cur: string; label?: (r: SalaryBreakdown) => string }) {
  const { t } = useTranslation();
  if (!rows.length) return <p className="px-5 pb-5 text-sm text-ink-muted">{t("salaryPage.noData")}</p>;
  return (
    <TableWrap>
      <table className="w-full min-w-[520px]">
        <thead className="border-b border-slate-100"><tr><th className="th pl-5">{t("salaryPage.colGroup")}</th><th className="th text-right">{t("salaryPage.colN")}</th><th className="th text-right">{t("salaryPage.colFloor")}</th><th className="th text-right">{t("salaryPage.colCeil")}</th><th className="th text-right">{t("salaryPage.colRange")}</th></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.key}>
              <td className="td pl-5 text-ink">{label ? label(r) : r.label ?? r.key}</td>
              <td className={cx("td text-right tabular", r.vacancies < 3 && "text-ink-faint")} title={r.vacancies < 3 ? t("salaryPage.small") : undefined}>{int(r.vacancies)}</td>
              <td className="td text-right tabular">{r.median_from !== null ? `${int(r.median_from)} ${cur}` : "—"}</td>
              <td className="td text-right tabular">{r.median_to !== null ? `${int(r.median_to)} ${cur}` : "—"}</td>
              <td className="td text-right tabular text-xs">{r.min_from !== null || r.max_to !== null ? `${int(r.min_from)} – ${int(r.max_to)}` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

export default function Salary() {
  const { t } = useTranslation();
  const [group, setGroup] = useState<{ currency: string; period: string } | null>(null);
  const [job, setJob] = useState<string | null>(null);
  const { tl } = useEscoLabels();
  const { data, error, loading, reload } = useApi<SalaryResponse>(`/api/salary${qs(group ?? {})}`);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const sel = data.selected;
  const cur = sel?.currency ?? "";

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("salaryPage.eyebrow")} title={t("salaryPage.title")} description={t("salaryPage.desc")} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("salaryPage.kCoverage")} value={pct(data.coverage_pct)} sub={t("salaryPage.kCoverageSub", { n: int(data.with_salary), t: int(data.total_vacancies) })} icon={<Wallet size={16} />} />
        <Stat label={t("salaryPage.kFloor", { c: cur })} value={sel ? int(sel.median_from) : "—"} sub={sel ? t("salaryPage.kFloorSub", { n: int(sel.with_from) }) : undefined} />
        <Stat label={t("salaryPage.kCeil", { c: cur })} value={sel ? int(sel.median_to) : "—"} sub={sel ? t("salaryPage.kCeilSub", { n: int(sel.with_to) }) : undefined} />
        <Stat label={t("salaryPage.kMid", { c: cur })} value={sel ? int(sel.median_midpoint) : "—"} sub={sel ? t("salaryPage.kMidSub", { n: int(sel.with_range) }) : undefined} />
      </div>

      <Card title={t("salaryPage.group")} subtitle={t("salaryPage.groupSub")}>
        <div className="flex flex-wrap gap-2">
          {data.groups.map((g) => {
            const active = sel?.currency === g.currency && sel?.period === g.period;
            return (
              <button key={`${g.currency}-${g.period}`} onClick={() => setGroup({ currency: g.currency, period: g.period })}
                className={cx("rounded-lg border px-4 py-2.5 text-left transition", active ? "border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500" : "border-slate-200 bg-white hover:border-slate-300")}>
                <div className="text-sm font-semibold text-ink">{g.currency} · {periodLabel(g.period)}</div>
                <div className="text-xs text-ink-muted tabular">{t("salaryPage.groupLine", { n: int(g.vacancies), m: int(g.median_from) })}</div>
              </button>
            );
          })}
        </div>
        {sel && (
          <p className="mt-3 text-xs text-ink-muted tabular">{t("salaryPage.iqr", { a: int(sel.p25_from), b: int(sel.p75_from), c: cur, min: int(sel.min_from), max: int(sel.max_to) })}</p>
        )}
      </Card>

      {!sel ? <div className="card"><Empty title={t("salaryPage.none")}>{t("salaryPage.noneHint")}</Empty></div> : (
        <>
          <div className="grid gap-6 xl:grid-cols-5">
            <Card className="xl:col-span-3" title={t("salaryPage.dist", { c: cur, p: periodLabel(sel.period) })}
              subtitle={t("salaryPage.distSub", { w: int(data.bin_width), c: cur })}>
              <Columns data={(data.histogram ?? []).map((b) => ({ ...b, bin: b.overflow ? `≥${int(b.from)}` : int(b.from) }))} x="bin" y="vacancies" height={260} yLabel={t("salaryPage.yLabel")}
                tooltip={(d) => [d.overflow ? t("salaryPage.top5", { bin: d.bin, c: cur }) : `${int(d.from as number)}–${int((d.to as number) - 1)} ${cur}`, [[t("salaryPage.colN"), int(d.vacancies as number)]]]} />
            </Card>
            <Card className="xl:col-span-2" title={t("salaryPage.covSource")} subtitle={t("salaryPage.covSourceSub")}>
              <RankBars data={data.coverage_by_source} label="source" value="coverage_pct" valueSuffix="%" maxLabel={18}
                tooltip={(d) => [d.source, [[t("skills.colVac"), int(d.vacancies)], [t("overview.withSalary"), int(d.with_salary)], [t("salaryPage.coverage"), pct(d.coverage_pct)]]]} />
            </Card>
          </div>
          <div className="grid gap-6 xl:grid-cols-2">
            <Card title={t("salaryPage.byOcc")} subtitle={t("salaryPage.byOccSub")} bodyClass="p-0 pt-2">
              <BreakdownTable rows={data.by_occupation ?? []} cur={cur} label={(r) => tl("occupation", r.key, r.label)} />
            </Card>
            <div className="min-w-0 space-y-6">
              <Card title={t("salaryPage.bySource")} bodyClass="p-0 pt-2"><BreakdownTable rows={data.by_source ?? []} cur={cur} /></Card>
              <Card title={t("salaryPage.byEmp")} bodyClass="p-0 pt-2"><BreakdownTable rows={data.by_employment_type ?? []} cur={cur} label={(r) => employment(r.key)} /></Card>
            </div>
          </div>
          <Card title={t("salaryPage.inGroup", { n: int(data.vacancies?.length ?? 0) })} bodyClass="p-0">
            <div className="max-h-[420px] overflow-y-auto">
              <TableWrap>
                <table className="w-full min-w-[560px]">
                  <thead className="sticky top-0 border-b border-slate-100 bg-white"><tr><th className="th pl-5">{t("salaryPage.colVac")}</th><th className="th">{t("salaryPage.colOcc")}</th><th className="th text-right">{t("salaryPage.colFrom")}</th><th className="th text-right">{t("salaryPage.colTo")}</th></tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.vacancies?.map((v) => (
                      <tr key={v.job_id} className="cursor-pointer hover:bg-slate-50" onClick={() => setJob(v.job_id)}>
                        <td className="td pl-5"><div className="text-ink">{v.title}</div><div className="text-xs text-ink-muted">{v.source_name}</div></td>
                        <td className="td text-xs">{v.occupation_label ? tl("occupation", v.occupation_uri, v.occupation_label) : <span className="text-ink-faint">{t("common.unmapped")}</span>}</td>
                        <td className="td text-right tabular">{v.salary_from !== null ? int(v.salary_from) : "—"}</td>
                        <td className="td text-right tabular">{v.salary_to !== null ? int(v.salary_to) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </div>
          </Card>
        </>
      )}
      <Card title={t("salaryPage.rules")}>
        <ul className="space-y-2 text-sm text-ink-soft">{["rule1", "rule2", "rule3", "rule4"].map((r) => <li key={r} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-600" />{t(`salaryPage.${r}`)}</li>)}</ul>
      </Card>
      <Note tone="warn" title={t("salaryPage.smallTitle")}>{t("salaryPage.smallText")}</Note>
      <VacancyDrawer jobId={job} onClose={() => setJob(null)} />
    </div>
  );
}
