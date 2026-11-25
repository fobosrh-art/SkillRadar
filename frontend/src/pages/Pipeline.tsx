import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, ChevronDown, ChevronRight, Clock, Database, Lock, RefreshCw, Timer } from "lucide-react";
import { useApi } from "../lib/api";
import { PipelineResponse, RunDetail } from "../lib/types";
import { ago, dateTime, hours, int, seconds } from "../lib/format";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, Stat, StatusBadge, TableWrap } from "../components/ui";
import { C, Columns } from "../components/charts";

const STATUS_COLOR: Record<string, string> = { success: C.good, blocked: C.warning, failed: C.critical };

function RunTasks({ runId }: { runId: string }) {
  const { t } = useTranslation();
  const { data, loading, error } = useApi<RunDetail>(`/api/pipeline/runs/${encodeURIComponent(runId)}`);
  if (loading && !data) return <Loading label={t("pipeline.loadingRun")} />;
  if (error || !data) return <ErrorBox message={error ?? "not found"} />;
  const rowMetrics = data.metrics.filter((m) => m.metric.startsWith("rows.") && (m.value ?? 0) > 0);
  const fresh = data.metrics.filter((m) => m.metric.startsWith("freshness."));
  return (
    <div className="grid gap-5 bg-slate-50/70 px-5 py-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("pipeline.tasks")}</div>
        <ol className="space-y-1.5">
          {data.tasks.map((tk, i) => (
            <li key={tk.task_name} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
              <span className="w-5 text-xs tabular text-ink-faint">{i + 1}</span>
              <span className="w-32 font-mono text-xs text-ink">{tk.task_name}</span>
              <StatusBadge status={tk.status} />
              <span className="text-xs text-ink-muted tabular">{seconds(tk.duration_s)}</span>
              {tk.attempts > 1 && <Badge tone="amber"><RefreshCw size={11} />{t("pipeline.attempts", { n: tk.attempts })}</Badge>}
              {tk.rows_out !== null && <span className="text-xs text-ink-muted tabular">{t("pipeline.rowsOut", { n: int(tk.rows_out) })}</span>}
              {tk.error && <span className="w-full break-words pl-8 text-xs text-rose-700">{tk.error}</span>}
              {tk.status === "skipped" && <span className="text-xs text-ink-muted">{t("pipeline.upstream")}</span>}
            </li>
          ))}
        </ol>
        {data.alerts.length > 0 && <div className="mt-3 space-y-1">{data.alerts.map((a, i) => <div key={i} className="flex gap-2 break-words text-xs text-amber-900"><AlertTriangle size={13} className="mt-0.5 shrink-0" />{a.message}</div>)}</div>}
      </div>
      <div className="space-y-4">
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("pipeline.rows")}</div>
          <div className="grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
            {rowMetrics.map((m) => <div key={m.metric} className="flex justify-between gap-2"><span className="truncate font-mono text-ink-muted">{m.metric.replace("rows.", "")}</span><span className="tabular text-ink">{int(m.value)}</span></div>)}
          </div>
        </div>
        {fresh.length > 0 && (
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("pipeline.freshness")}</div>
            {fresh.map((m) => { const k = m.metric.replace("freshness.", ""); return <div key={m.metric} className="flex justify-between gap-2 text-xs"><span className="text-ink-muted">{t(`pipeline.fresh.${k}`, { defaultValue: k })}</span><span className="tabular">{hours(m.value)}</span></div>; })}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Pipeline() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useApi<PipelineResponse>("/api/pipeline", { pollMs: 15000 });
  const [open, setOpen] = useState<string | null>(null);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const last = data.runs[0];
  const pub = data.current_publication;
  const chart = [...data.runs].reverse().map((r, i) => ({ ...r, n: `#${i + 1}`, dur: r.duration_s ?? 0 }));
  const sched = data.scheduler.state;
  const runType = (v: string) => t(`pipeline.runType.${v}`, { defaultValue: v });
  const trig = (v: string) => t(`pipeline.trigger.${v}`, { defaultValue: v });

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("pipeline.eyebrow")} title={t("pipeline.title")} description={<>{t("pipeline.intro")} {t("pipeline.desc")}</>}
        actions={<><button className="btn-secondary" onClick={reload}><RefreshCw size={15} />{t("common.refresh")}</button><Link to="/operations" className="btn-primary">{t("pipeline.ops")}</Link></>} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label={t("pipeline.kRuns")} value={int(data.runs.length)} icon={<Database size={16} />}
          sub={Object.entries(data.status_counts).map(([k, v]) => `${int(v)} ${t(`status.${k}`, { defaultValue: k }).toLowerCase()}`).join(" · ")} />
        <Stat label={t("pipeline.kLast")} value={last ? <StatusBadge status={last.status} /> : "—"} sub={last ? `${dateTime(last.started_at)} · ${trig(last.trigger)}` : undefined} />
        <Stat label={t("pipeline.kDur")} value={seconds(last?.duration_s)} icon={<Timer size={16} />} sub={last ? t("pipeline.kDurSub", { t: runType(last.run_type) }) : undefined} />
        <Stat label={t("pipeline.kGold")} value={pub ? `v${pub.version}` : "—"} sub={pub ? t("pipeline.kGoldSub", { n: int(pub.vacancy_count), ago: ago(pub.published_at) }) : t("pipeline.kGoldNone")} />
        <Stat label={t("pipeline.kFresh")} value={hours(pub?.freshness.snapshot_at_age_hours)} icon={<Clock size={16} />}
          sub={pub ? t("pipeline.kFreshSub", { h: hours(pub.freshness.posted_at_age_hours) }) : undefined} />
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3" title={t("pipeline.duration")} subtitle={t("pipeline.durationSub")}>
          <Columns data={chart} x="n" y="dur" height={220} colorOf={(d) => STATUS_COLOR[d.status as string] ?? C.neutral}
            tooltip={(d) => [`${d.n} · ${runType(d.run_type as string)} (${trig(d.trigger as string)})`, [[t("pipeline.status"), t(`status.${d.status}`, { defaultValue: d.status as string })], [t("pipeline.dur"), seconds(d.dur as number)], [t("pipeline.started"), dateTime(d.started_at as string)]]]} />
          <div className="mt-2 flex flex-wrap gap-4 text-xs text-ink-muted">
            {Object.entries(STATUS_COLOR).map(([k, col]) => <span key={k} className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: col }} />{t(`status.${k}`)}</span>)}
          </div>
        </Card>
        <Card className="xl:col-span-2" title={t("pipeline.sched")}>
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between gap-2"><span className="text-ink-muted">{t("pipeline.webSched")}</span>{data.scheduler.web.enabled ? <StatusBadge status="running" label={t("pipeline.every", { h: data.scheduler.web.interval_hours })} /> : <Badge>{t("status.off")}</Badge>}</div>
            {data.scheduler.web.next_run_at && <div className="flex justify-between gap-2"><span className="text-ink-muted">{t("pipeline.nextRun")}</span><span>{dateTime(data.scheduler.web.next_run_at)}</span></div>}
            {sched && <>
              <div className="flex justify-between gap-2"><span className="text-ink-muted">{t("pipeline.lastMode")}</span><span>{sched.mode} {sched.live ? t("pipeline.modeLive") : t("pipeline.modeLocal")}</span></div>
              <div className="flex justify-between gap-2"><span className="text-ink-muted">{t("pipeline.lastSched")}</span><span className="text-right">{sched.last_run_at ? <>{dateTime(sched.last_run_at)} · {t(`status.${sched.last_status}`, { defaultValue: sched.last_status ?? "" })}</> : "—"}</span></div>
              <div className="flex justify-between gap-2"><span className="text-ink-muted">{t("pipeline.heartbeat")}</span><span>{ago(sched.heartbeat_at)}</span></div>
            </>}
            <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-3"><span className="inline-flex items-center gap-1.5 text-ink-muted"><Lock size={14} />{t("pipeline.lock")}</span>{data.lock ? <StatusBadge status="running" label={data.lock.run_id} /> : <Badge tone="emerald">{t("status.free")}</Badge>}</div>
            <p className="text-xs leading-5 text-ink-muted">{t("pipeline.lockNote")}</p>
          </div>
        </Card>
      </div>

      <Card title={t("pipeline.history")} subtitle={t("pipeline.historySub")} bodyClass="p-0">
        <TableWrap>
          <table className="w-full min-w-[860px]">
            <thead className="border-b border-slate-100"><tr>
              <th className="th pl-5" /><th className="th">{t("pipeline.colStarted")}</th><th className="th">{t("pipeline.colType")}</th><th className="th">{t("pipeline.colTrigger")}</th><th className="th">{t("pipeline.colStatus")}</th><th className="th">{t("pipeline.colTasks")}</th><th className="th text-right">{t("pipeline.colRetries")}</th><th className="th text-right">{t("pipeline.colDur")}</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {data.runs.map((r) => (
                <Fragment key={r.run_id}>
                  <tr className="cursor-pointer hover:bg-slate-50" onClick={() => setOpen(open === r.run_id ? null : r.run_id)}>
                    <td className="td pl-5 text-ink-faint">{open === r.run_id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</td>
                    <td className="td whitespace-nowrap"><div className="text-ink">{dateTime(r.started_at)}</div><div className="font-mono text-[11px] text-ink-faint">{r.run_id}</div></td>
                    <td className="td">{runType(r.run_type)}{r.params.start ? <div className="text-xs text-ink-muted">{String(r.params.start)} → {String(r.params.end)}</div> : null}{r.params.live ? <div className="text-xs text-ink-muted">{t("pipeline.liveFetch")}</div> : null}</td>
                    <td className="td">{trig(r.trigger)}</td>
                    <td className="td"><StatusBadge status={r.status} />{r.error && <div className="mt-1 max-w-xs truncate text-xs text-ink-muted" title={r.error}>{r.error}</div>}</td>
                    <td className="td"><div className="flex gap-1">{r.tasks.map((tk) => (
                      <span key={tk.task_name} title={`${tk.task_name}: ${t(`status.${tk.status}`, { defaultValue: tk.status })}`} className="h-2.5 w-5 rounded-sm" style={{ background: tk.status === "success" ? C.good : tk.status === "skipped" ? "#cbd5e1" : tk.status === "blocked" ? C.warning : C.critical }} />
                    ))}</div></td>
                    <td className="td text-right tabular">{int(r.retries)}</td>
                    <td className="td text-right tabular">{seconds(r.duration_s)}</td>
                  </tr>
                  {open === r.run_id && <tr><td colSpan={8} className="p-0"><RunTasks runId={r.run_id} /></td></tr>}
                </Fragment>
              ))}
            </tbody>
          </table>
        </TableWrap>
        {data.runs.length === 0 && <Empty title={t("pipeline.noRuns")} />}
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title={t("pipeline.versions")} subtitle={t("pipeline.versionsSub")} bodyClass="p-0">
          <div className="max-h-[420px] overflow-y-auto">
            <TableWrap>
              <table className="w-full min-w-[460px]">
                <thead className="sticky top-0 border-b border-slate-100 bg-white"><tr><th className="th pl-5">{t("pipeline.colVersion")}</th><th className="th">{t("pipeline.colPublished")}</th><th className="th text-right">{t("pipeline.colVac")}</th><th className="th">{t("pipeline.colRun")}</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {data.publications.map((p) => (
                    <tr key={p.version}>
                      <td className="td pl-5 font-medium text-ink">v{p.version} {pub?.version === p.version && <Badge tone="indigo">{t("pipeline.liveBadge")}</Badge>}</td>
                      <td className="td">{dateTime(p.published_at)}</td>
                      <td className="td text-right tabular">{int(p.vacancy_count)}</td>
                      <td className="td font-mono text-[11px] text-ink-muted">{p.run_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </div>
        </Card>
        <Card title={t("pipeline.alerts", { n: data.alerts.length })} subtitle={t("pipeline.alertsSub")}>
          {data.alerts.length === 0 ? <Empty title={t("pipeline.noAlerts")}>{t("pipeline.noAlertsHint")}</Empty> : (
            <ul className="max-h-[420px] space-y-2 overflow-y-auto">
              {data.alerts.map((a) => (
                <li key={a.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                  <div className="flex items-center justify-between gap-2"><StatusBadge status={a.level === "error" ? "error" : "warning"} /><span className="text-xs text-ink-muted">{dateTime(a.created_at)}</span></div>
                  <p className="mt-1.5 break-words text-ink-soft" lang="en">{a.message}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
