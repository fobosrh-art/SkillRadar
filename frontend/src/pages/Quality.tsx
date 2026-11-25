import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, ShieldCheck } from "lucide-react";
import { useApi } from "../lib/api";
import { QualityResponse } from "../lib/types";
import { dateTime, int } from "../lib/format";
import { Badge, Card, Empty, ErrorBox, Loading, Meter, Note, PageHeader, Stat, StatusBadge, TableWrap } from "../components/ui";

export default function Quality() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useApi<QualityResponse>("/api/quality");
  const [open, setOpen] = useState<string | null>(null);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data || !data.run) return <Empty title={t("quality.none")} icon={<ShieldCheck size={28} />}>{t("quality.noneHint")}</Empty>;

  const blocking = data.checks.filter((c) => c.severity === "blocking");
  const passed = data.checks.filter((c) => c.passed).length;
  const history = Object.fromEntries(data.history.map((h) => [h.check_name, h]));
  const name = (c: string) => t(`quality.check.${c}.0`, { defaultValue: c });
  const rule = (c: string) => t(`quality.check.${c}.1`, { defaultValue: "" });

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("quality.eyebrow")} title={t("quality.title")} description={<>{t("quality.gate")} {t("quality.intro")}</>} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("quality.kPassed")} value={`${passed}/${data.checks.length}`} tone={passed === data.checks.length ? "good" : "bad"} />
        <Stat label={t("quality.kBlocking")} value={`${blocking.filter((c) => c.passed).length}/${blocking.length}`} sub={t("quality.kBlockingSub")} />
        <Stat label={t("quality.kLast")} value={<StatusBadge status={data.run.status} />} sub={dateTime(data.run.started_at)} />
        <Stat label={t("quality.kRuns")} value={int(data.runs.length)} sub={t("quality.kRunsSub", { n: int(data.runs.filter((r) => r.passed === r.total).length) })} />
      </div>

      <Card title={t("quality.latest")} subtitle={t("quality.latestSub", { id: data.run.run_id })} bodyClass="p-0">
        <TableWrap>
          <table className="w-full min-w-[900px]">
            <thead className="border-b border-slate-100"><tr>
              <th className="th pl-5" /><th className="th">{t("quality.colCheck")}</th><th className="th">{t("quality.colSeverity")}</th><th className="th">{t("quality.colResult")}</th><th className="th text-right">{t("quality.colChecked")}</th><th className="th text-right">{t("quality.colFailed")}</th><th className="th">{t("quality.colHistory")}</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {data.checks.map((c) => {
                const h = history[c.check_name];
                return (
                  <Fragment key={c.check_name}>
                    <tr className="cursor-pointer hover:bg-slate-50" onClick={() => setOpen(open === c.check_name ? null : c.check_name)}>
                      <td className="td pl-5 text-ink-faint">{open === c.check_name ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</td>
                      <td className="td"><div className="font-medium text-ink">{name(c.check_name)}</div><div className="font-mono text-[11px] text-ink-faint">{c.check_name}</div><div className="mt-0.5 max-w-md text-xs leading-5 text-ink-muted">{rule(c.check_name)}</div><div className="mt-1 max-w-md text-xs leading-5 text-indigo-800">{t("quality.whyLabel")} {t(`quality.why.${c.check_name}`, { defaultValue: "" })}</div></td>
                      <td className="td"><Badge tone={c.severity === "blocking" ? "indigo" : "slate"}>{t(`quality.severity.${c.severity}`)}</Badge></td>
                      <td className="td"><StatusBadge status={c.passed ? "pass" : c.severity === "warning" ? "warn" : "fail"} /></td>
                      <td className="td text-right tabular">{int(c.checked_count)}</td>
                      <td className={`td text-right tabular ${c.failed_count ? "font-semibold text-rose-700" : ""}`}>{int(c.failed_count)}</td>
                      <td className="td">{h && <div className="w-36"><div className="mb-1 text-xs tabular text-ink-muted">{t("quality.runsPassed", { p: h.passed, n: h.runs })}</div><Meter value={h.passed} max={h.runs} /></div>}</td>
                    </tr>
                    {open === c.check_name && (
                      <tr><td colSpan={7} className="bg-slate-50/70 px-5 py-4 text-sm">
                        <div className="break-words text-ink-soft"><span className="font-medium text-ink">{t("quality.detail")}</span> <span lang="en">{c.detail || "—"}</span></div>
                        {c.sample.length > 0 ? (
                          <pre className="mt-2 max-h-56 overflow-auto rounded-lg border border-slate-200 bg-white p-3 font-mono text-xs text-ink-soft">{JSON.stringify(c.sample, null, 2)}</pre>
                        ) : <div className="mt-1 text-xs text-ink-muted">{t("quality.noFailing")}</div>}
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </TableWrap>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title={t("quality.perRun")} bodyClass="p-0">
          <div className="max-h-[420px] overflow-y-auto">
            <TableWrap>
              <table className="w-full min-w-[420px]">
                <thead className="sticky top-0 border-b border-slate-100 bg-white"><tr><th className="th pl-5">{t("quality.colRun")}</th><th className="th">{t("quality.colStatus")}</th><th className="th text-right">{t("quality.colPassed")}</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {data.runs.map((r) => (
                    <tr key={r.run_id}><td className="td pl-5">{dateTime(r.started_at)}<div className="font-mono text-[11px] text-ink-faint">{r.run_id}</div></td>
                      <td className="td"><StatusBadge status={r.status} /></td><td className="td text-right tabular">{r.passed}/{r.total}</td></tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </div>
        </Card>
        <Card title={t("quality.issues")} subtitle={t("quality.issuesSub")}>
          {data.normalization_issues.length === 0 ? <Empty title={t("quality.noIssues")} /> : (
            <ul className="space-y-2 text-sm">
              {data.normalization_issues.map((i) => (
                <li key={i.field + i.issue} className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 p-3">
                  <div><div className="font-mono text-xs text-ink">{i.field}</div><div className="text-xs text-ink-muted">{t(`quality.issue.${i.issue}`, { defaultValue: i.issue.replace(/_/g, " ") })}</div></div>
                  <span className="tabular font-medium">{int(i.n)}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4"><Note>{t("quality.silverNote")}</Note></div>
        </Card>
      </div>
    </div>
  );
}
