import { ReactNode, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarRange, CheckCircle2, CloudDownload, FlaskConical, Lock, Play, Timer, XCircle } from "lucide-react";
import { ApiError, api, useApi } from "../lib/api";
import { AdminStatus, DemoStep, Operation } from "../lib/types";
import { dateTime, int, seconds } from "../lib/format";
import { Badge, Card, Dialog, ErrorBox, Loading, Note, PageHeader, StatusBadge, TableWrap } from "../components/ui";

function ActionCard({ icon, title, children, action }: { icon: ReactNode; title: string; children: ReactNode; action: ReactNode }) {
  return (
    <div className="card flex flex-col p-5">
      <div className="flex items-center gap-2.5"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700">{icon}</span><h2 className="text-sm font-semibold">{title}</h2></div>
      <div className="mt-3 flex-1 text-sm leading-6 text-ink-muted">{children}</div>
      <div className="mt-4">{action}</div>
    </div>
  );
}

function DemoResult({ op }: { op: Operation }) {
  const { t } = useTranslation();
  const demo = (op.result as { demo?: { demo: string; steps: DemoStep[]; passed: boolean; sandbox: string } } | null)?.demo;
  if (!demo) return null;
  const dates = demo.steps.find((s) => Array.isArray(s.available_dates))?.available_dates as string[] | undefined;
  return (
    <div className="mt-3 space-y-2">
      <div className={demo.passed ? "rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs leading-5 text-emerald-900" : "rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs leading-5 text-rose-900"}>
        <div className="font-semibold">{demo.passed ? t("ops.demoPassed") : t("ops.demoFailed")}</div>
        <div>{t("ops.demoChecked", { what: t(`ops.demo.${demo.demo}.0`, { defaultValue: demo.demo }) })} {t(`ops.demoWhy.${demo.demo}`, { defaultValue: "" })}</div>
        <div className="mt-1">{t("ops.demoReading")}</div>
      </div>
      {dates && <div className="text-xs text-ink-muted">{t("ops.dates", { d: dates.join(", ") })}</div>}
      {demo.steps.map((s) => {
        const vars = (s.vars ?? {}) as Record<string, string>;
        const title = t(`ops.steps.${demo.demo}.${s.step - 1}.0`, { ...vars, defaultValue: s.title });
        const expected = t(`ops.steps.${demo.demo}.${s.step - 1}.1`, { ...vars, defaultValue: s.expected });
        return (
          <div key={s.step} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <div className="flex items-start gap-2">
              {s.ok ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-600" /> : <XCircle size={16} className="mt-0.5 shrink-0 text-rose-600" />}
              <div className="min-w-0 flex-1">
                <div className="break-words font-medium text-ink">{t("ops.step", { n: s.step, t: title })}</div>
                <div className="text-xs text-ink-muted">{t("ops.expected", { e: expected })}</div>
                <div className="mt-1.5 flex flex-wrap gap-1.5 text-xs">
                  {s.run_status && <StatusBadge status={s.run_status} />}
                  <Badge>{s.state.gold_version ? t("ops.goldV", { v: `v${s.state.gold_version}` }) : t("ops.goldNone")}</Badge>
                  <Badge>{t("ops.hash", { h: s.state.gold_sha256 })}</Badge>
                  <Badge>{t("ops.bronze", { n: int(s.state.bronze_rows) })}</Badge>
                  {typeof s.state.error_alerts === "number" && <Badge>{t("ops.alertsN", { n: s.state.error_alerts })}</Badge>}
                  {typeof s.http_attempts === "number" && <Badge>{t("ops.attemptsN", { n: s.http_attempts })}</Badge>}
                </div>
                {Array.isArray(s.failed_checks) && (s.failed_checks as { check: string; failed: number }[]).map((f) => (
                  <div key={f.check} className="mt-1 text-xs text-amber-800">{t("ops.failedCheck", { c: f.check, n: f.failed })}</div>
                ))}
              </div>
            </div>
          </div>
        );
      })}
      <div className="break-all text-xs text-ink-muted">{t("ops.sandbox", { p: demo.sandbox })}</div>
    </div>
  );
}

export default function Operations() {
  const { t } = useTranslation();
  const status = useApi<AdminStatus>("/api/admin/status", { pollMs: 3000 });
  const [ops, setOps] = useState<Operation[]>([]);
  const [opsErr, setOpsErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [confirmLive, setConfirmLive] = useState(false);
  const [ack, setAck] = useState(false);
  const [pages, setPages] = useState(1);
  const [start, setStart] = useState("2026-11-24");
  const [end, setEnd] = useState("2026-11-24");
  const [hours, setHours] = useState(6);

  const st = status.data;
  const local = !!st?.local;
  const busy = !!st?.busy || !!st?.db_lock;
  const errText = (e: unknown) => {
    const err = e as ApiError;
    if (err.status === 409) return t("errors.busy");
    if (err.status === 403) return t("errors.forbidden");
    return t("errors.generic", { msg: err.message });
  };

  const loadOps = () => {
    if (!local) return;
    api.admin<Operation[]>("/api/admin/operations?limit=25", undefined, "GET")
      .then((o) => { setOps(o); setOpsErr(null); })
      .catch((e: Error) => setOpsErr(e.message));
  };
  useEffect(() => {
    loadOps();
  }, [local, st?.busy, st?.current_operation]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(loadOps, 1500);
    return () => clearInterval(timer);
  }, [busy]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (path: string, body?: unknown) => {
    setMsg(null);
    try {
      const op = await api.admin<Operation>(path, body);
      setSelected(op.op_id);
      setMsg({ tone: "ok", text: t("ops.started", { k: op.kind, id: op.op_id }) });
      status.reload();
      loadOps();
    } catch (e) {
      setMsg({ tone: "err", text: errText(e) });
    }
  };
  const toggleScheduler = (enabled: boolean, runNow = false) =>
    api.admin("/api/admin/scheduler", { enabled, interval_hours: hours, run_now: runNow })
      .then(() => { status.reload(); setMsg({ tone: "ok", text: enabled ? t("ops.schedEnabled", { h: hours }) : t("ops.schedStopped") }); })
      .catch((e) => setMsg({ tone: "err", text: errText(e) }));

  if (status.loading && !st) return <Loading />;
  if (status.error) return <ErrorBox message={status.error} onRetry={status.reload} />;
  const sel = ops.find((o) => o.op_id === selected) ?? ops[0];

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("ops.eyebrow")} title={t("ops.title")} description={t("ops.desc")}
        actions={busy ? <StatusBadge status="running" label={st?.current_operation ?? st?.db_lock?.run_id ?? t("status.running")} /> : <StatusBadge status="success" label={t("status.idle")} />} />

      {!local && <Note tone="warn" title={t("ops.readOnly")}>{t("ops.readOnlyText")}</Note>}
      {msg && <div className={msg.tone === "ok" ? "break-words rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900" : "break-words rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900"}>{msg.text}</div>}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ActionCard icon={<Play size={18} />} title={t("ops.runTitle")} action={<button className="btn-primary w-full" disabled={!local || busy} onClick={() => submit("/api/admin/run")}><Play size={15} />{t("ops.runBtn")}</button>}>
          {t("ops.runText")}
        </ActionCard>
        <ActionCard icon={<CloudDownload size={18} />} title={t("ops.liveTitle")}
          action={<button className="btn-secondary w-full" disabled={!local || busy || !st?.api_key_configured || (st?.budget_remaining ?? 0) < 1} onClick={() => { setAck(false); setPages(1); setConfirmLive(true); }}><CloudDownload size={15} />{t("ops.liveBtn")}</button>}>
          {t("ops.liveText")}<b className="tabular text-ink">{int(st?.budget_remaining)}</b>.
          {!st?.api_key_configured && <span className="block text-amber-700">{t("ops.noKey")}</span>}
        </ActionCard>
        <ActionCard icon={<CalendarRange size={18} />} title={t("ops.bfTitle")}
          action={<button className="btn-secondary w-full" disabled={!local || busy || !start || !end} onClick={() => submit("/api/admin/backfill", { start, end })}><CalendarRange size={15} />{t("ops.bfBtn")}</button>}>
          <div className="grid grid-cols-2 gap-2">
            <label><span className="label">{t("ops.bfFrom")}</span><input type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} /></label>
            <label><span className="label">{t("ops.bfTo")}</span><input type="date" className="input" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
          </div>
          <p className="mt-2 text-xs">{t("ops.bfText")}</p>
        </ActionCard>
        <ActionCard icon={<Timer size={18} />} title={t("ops.schedTitle")}
          action={st?.scheduler.enabled
            ? <button className="btn-secondary w-full" disabled={!local} onClick={() => toggleScheduler(false)}>{t("ops.stop")}</button>
            : <div className="flex flex-wrap gap-2"><button className="btn-secondary flex-1" disabled={!local} onClick={() => toggleScheduler(true)}>{t("ops.enable")}</button><button className="btn-secondary flex-1" disabled={!local || busy} onClick={() => toggleScheduler(true, true)}>{t("ops.enableRun")}</button></div>}>
          {st?.scheduler.enabled ? t("ops.schedOn", { h: st.scheduler.interval_hours, at: dateTime(st.scheduler.next_run_at) }) : t("ops.schedOff")}
          {!st?.scheduler.enabled && <label className="mt-2 flex items-center gap-2 text-xs">{t("ops.schedEvery")} <input type="number" min={0.1} step={0.5} className="input w-20 py-1" value={hours} onChange={(e) => setHours(Number(e.target.value))} /> {t("ops.schedHours")}</label>}
        </ActionCard>
      </div>

      <Card title={<span className="inline-flex items-center gap-2"><FlaskConical size={15} />{t("ops.demos")}</span>} subtitle={t("ops.demosSub")}>
        <div className="grid gap-3 md:grid-cols-2">
          {Object.keys(st?.demos ?? {}).map((name) => (
            <div key={name} className="flex flex-col rounded-xl border border-slate-200 p-4">
              <div className="text-sm font-semibold text-ink">{t(`ops.demo.${name}.0`, { defaultValue: name })}</div>
              <p className="mt-1 text-sm leading-6 text-ink-muted">{t(`ops.demo.${name}.1`, { defaultValue: st?.demos[name] })}</p>
              <p className="mt-2 flex-1 text-xs leading-5 text-indigo-800">{t(`ops.demoWhy.${name}`, { defaultValue: "" })}</p>
              <button className="btn-secondary mt-3 self-start" disabled={!local || busy} onClick={() => submit(`/api/admin/demo/${name}`)}><FlaskConical size={15} />{t("ops.runDemo")}</button>
            </div>
          ))}
        </div>
      </Card>

      {local && (
        <div className="grid gap-6 xl:grid-cols-5">
          <Card className="xl:col-span-2" title={t("ops.log")} bodyClass="p-0">
            {opsErr && <div className="p-4"><ErrorBox message={opsErr} /></div>}
            {ops.length === 0 ? <p className="p-5 text-sm text-ink-muted">{t("ops.noOps")}</p> : (
              <div className="max-h-[520px] overflow-y-auto">
                <TableWrap>
                  <table className="w-full min-w-[380px]">
                    <thead className="sticky top-0 border-b border-slate-100 bg-white"><tr><th className="th pl-5">{t("ops.colRequested")}</th><th className="th">{t("ops.colOp")}</th><th className="th">{t("ops.colStatus")}</th></tr></thead>
                    <tbody className="divide-y divide-slate-100">
                      {ops.map((o) => (
                        <tr key={o.op_id} onClick={() => setSelected(o.op_id)} className={`cursor-pointer hover:bg-slate-50 ${sel?.op_id === o.op_id ? "bg-indigo-50/60" : ""}`}>
                          <td className="td pl-5 text-xs">{dateTime(o.requested_at)}</td><td className="td font-mono text-xs">{o.kind}</td><td className="td"><StatusBadge status={o.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TableWrap>
              </div>
            )}
          </Card>
          <Card className="xl:col-span-3" title={t("ops.details")}>
            {!sel ? <p className="text-sm text-ink-muted">{t("ops.select")}</p> : (
              <div className="text-sm">
                <div className="flex flex-wrap items-center gap-2"><span className="break-all font-mono text-xs">{sel.op_id}</span><StatusBadge status={sel.status} /><Badge>{sel.kind}</Badge></div>
                <div className="mt-2 grid gap-1 text-xs text-ink-muted sm:grid-cols-2">
                  <div>{t("ops.startedAt", { t: dateTime(sel.started_at) })}</div><div>{t("ops.finishedAt", { t: dateTime(sel.finished_at) })}</div>
                  {sel.run_id && <div className="break-all">{t("ops.pipelineRun")}<span className="font-mono">{sel.run_id}</span></div>}
                  {sel.result && typeof sel.result.duration_s === "number" && <div>{t("ops.duration", { d: seconds(sel.result.duration_s as number) })}</div>}
                </div>
                {sel.error && <div className="mt-3 break-words rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900" lang="en">{sel.error}</div>}
                {!!sel.result?.tasks && typeof sel.result.tasks === "object" && (
                  <div className="mt-3 flex flex-wrap gap-1.5">{Object.entries(sel.result.tasks as Record<string, string>).map(([k, v]) => <span key={k} className="inline-flex items-center gap-1 text-xs"><span className="font-mono">{k}</span><StatusBadge status={v} /></span>)}</div>
                )}
                <DemoResult op={sel} />
              </div>
            )}
          </Card>
        </div>
      )}

      <Note title={t("ops.protection")}><span className="inline-flex items-start gap-1.5"><Lock size={13} className="mt-1 shrink-0" />{t("ops.protText")}</span></Note>

      <Dialog open={confirmLive} onClose={() => setConfirmLive(false)} title={t("ops.dlgTitle")}
        footer={<><button className="btn-secondary" onClick={() => setConfirmLive(false)}>{t("ops.cancel")}</button>
          <button className="btn-primary" disabled={!ack} onClick={() => { setConfirmLive(false); submit("/api/admin/fetch-live", { confirm: true, max_pages: pages }); }}>{t("ops.fetchN", { n: pages })}</button></>}>
        <p>{t("ops.dlgText", { n: int(st?.budget_remaining) })}</p>
        <label className="mt-4 block"><span className="label">{t("ops.dlgPages")}</span>
          <select className="input" value={pages} onChange={(e) => setPages(Number(e.target.value))}>
            {[1, 2, 3].map((n) => <option key={n} value={n} disabled={n > (st?.budget_remaining ?? 0)}>{n} {n === 1 ? t("ops.dlgDefault") : ""}</option>)}
          </select></label>
        <label className="mt-4 flex items-start gap-2"><input type="checkbox" className="mt-1" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          <span>{t("ops.dlgConfirm", { p: pages, n: int(st?.budget_remaining) })}</span></label>
      </Dialog>
    </div>
  );
}
