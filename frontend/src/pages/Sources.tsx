import { ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowRight, Cloud, Database, FileJson, Globe, KeyRound, Layers, MonitorSmartphone, Server, ShieldCheck, Table2 } from "lucide-react";
import { useApi } from "../lib/api";
import { SourcesResponse } from "../lib/types";
import { dateTime, int, pct, skillType } from "../lib/format";
import { Badge, Card, ErrorBox, KeyValue, Loading, Meter, Note, PageHeader, Stat, StatusBadge, TableWrap, cx } from "../components/ui";

type NodeId = "sources" | "landing" | "bronze" | "silver" | "gate" | "gold" | "api" | "web";
const NODES: { id: NodeId; icon: ReactNode }[] = [
  { id: "sources", icon: <Cloud size={15} /> }, { id: "landing", icon: <FileJson size={15} /> }, { id: "bronze", icon: <Layers size={15} /> },
  { id: "silver", icon: <Table2 size={15} /> }, { id: "gate", icon: <ShieldCheck size={15} /> }, { id: "gold", icon: <Database size={15} /> },
  { id: "api", icon: <Server size={15} /> }, { id: "web", icon: <MonitorSmartphone size={15} /> },
];


function FlowNode({ active, onClick, icon, title, metric, sub }: {
  active: boolean; onClick: () => void; icon: ReactNode; title: string; metric: string; sub: string;
}) {
  return (
    <button onClick={onClick}
      className={cx("h-full w-full rounded-xl border bg-white p-3 text-left transition",
        active ? "border-indigo-500 ring-2 ring-indigo-500/20" : "border-slate-200 hover:border-indigo-300")}>
      <div className="flex items-center gap-2 text-xs font-semibold text-ink">
        <span className={cx("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg", active ? "bg-indigo-600 text-white" : "bg-indigo-50 text-indigo-700")}>{icon}</span>
        <span className="min-w-0 [overflow-wrap:normal] [word-break:normal] hyphens-auto">{title}</span>
      </div>
      <div className="mt-2 text-sm font-semibold tabular text-ink">{metric}</div>
      <div className="text-[11px] leading-4 text-ink-muted">{sub}</div>
    </button>
  );
}

export default function Sources() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useApi<SourcesResponse>("/api/sources");
  const [node, setNode] = useState<NodeId>("bronze");
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const s = data.softon;
  const L = data.layers;
  const layerTables = (prefix: string) => Object.entries(L).filter(([k]) => k.startsWith(prefix));
  const metric: Record<NodeId, string> = {
    sources: t("sources.n.sources.1"), landing: t("sources.n.landing.1", { n: s.files.length }), bronze: t("sources.bronzeMetric", { v: int(L["bronze_softon_jobs"] ?? 0) }),
    silver: int(L["silver_vacancies"] ?? 0), gate: t("sources.n.gate.1"), gold: int(L["gold_vacancies"] ?? 0), api: "/api", web: "React",
  };
  const budgetUsedPct = s.budget.monthly_budget ? (s.budget.used_this_month / s.budget.monthly_budget) * 100 : 0;
  const kind = (k: string) => t(`sources.kind.${k}`, { defaultValue: k });

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("sources.eyebrow")} title={t("sources.title")} description={<>{t("sources.desc")} {t("sources.why")}</>} />

      <Card title={t("sources.flow")} subtitle={t("sources.flowSub")}>
        <div className="flex flex-col gap-2 xl:flex-row xl:items-stretch">
          {NODES.flatMap((n, i) => {
            const el = (
              <div key={n.id} className="min-w-0 xl:flex-1">
                <FlowNode active={node === n.id} onClick={() => setNode(n.id)} icon={n.icon}
                  title={t(`sources.n.${n.id}.0`)} metric={metric[n.id]} sub={t(`sources.n.${n.id}.2`)} />
              </div>
            );
            return i < NODES.length - 1
              ? [el, <div key={`${n.id}-a`} className="flex shrink-0 items-center justify-center text-ink-faint"><ArrowRight size={18} className="hidden xl:block" /><ArrowDown size={18} className="xl:hidden" /></div>]
              : [el];
          })}
        </div>
        <div className="mt-4 rounded-xl bg-slate-50 p-4 text-sm leading-6 text-ink-soft">
          {t(`sources.d.${node}`, { city: s.city, n: s.files.length })}
          {node === "bronze" && <div className="mt-2 font-medium text-ink">{t("sources.bronzeSplit", { v: int(L["bronze_softon_jobs"] ?? 0), e: int((L["bronze_esco_skills"] ?? 0) + (L["bronze_esco_occupations"] ?? 0) + (L["bronze_esco_occupation_skills"] ?? 0)) })}</div>}
          {(node === "bronze" || node === "silver" || node === "gold") && (
            <div className="mt-3 grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2 lg:grid-cols-3">
              {layerTables(`${node}_`).map(([k, v]) => <div key={k} className="flex justify-between gap-2"><span className="truncate font-mono text-ink-muted">{k}</span><span className="tabular text-ink">{int(v)}</span></div>)}
            </div>
          )}
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("sources.kRaw")} value={int(s.bronze_records)} sub={t("sources.kRawSub", { n: int(s.distinct_ids) })} />
        <Stat label={t("sources.kGold")} value={int(s.published_vacancies)} sub={t("sources.kGoldSub", { n: int(s.cross_source_duplicates) })} />
        <Stat label={t("sources.kEsco")} value={`${int(data.esco.skills)} · ${int(data.esco.occupations)}`} sub={t("sources.kEscoSub", { n: int(data.esco.relations) })} />
        <Stat label={t("sources.kBudget")} value={int(s.budget.remaining)} sub={t("sources.kBudgetSub", { u: int(s.budget.used_this_month), b: int(s.budget.monthly_budget) })} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title={<span className="inline-flex items-center gap-2"><Globe size={15} />{t("sources.softon")}</span>}
          actions={s.api_key_configured ? <StatusBadge status="success" label={t("sources.keyOk")} /> : <StatusBadge status="warning" label={t("sources.keyNo")} />}>
          <KeyValue items={[
            [t("sources.endpoint"), <code className="break-all text-xs">{s.base_url}/jobs</code>],
            [t("sources.query"), <code className="break-all text-xs">city={s.city} · limit={s.page_limit} · include=bodies</code>],
            [t("sources.auth"), <span className="inline-flex items-center gap-1.5"><KeyRound size={13} />{t("sources.authVal")}</span>],
            [t("sources.lastQuota"), s.budget.last_quota ? `${s.budget.last_quota.quota_used} / ${s.budget.last_quota.quota_limit} (${dateTime(s.budget.last_quota.requested_at)})` : t("sources.noLive")],
          ]} />
          <div className="mt-5">
            <div className="mb-1.5 flex justify-between gap-2 text-xs"><span className="text-ink-muted">{t("sources.budget")}</span><span className="tabular">{t("sources.budgetLine", { u: int(s.budget.used_this_month), l: int(s.budget.remaining) })}</span></div>
            <Meter value={budgetUsedPct} className="h-2" />
          </div>
          <div className="mt-5 rounded-xl border border-slate-200 p-4">
            <div className="mb-3 text-sm font-medium text-ink">{t("sources.incr")}</div>
            <KeyValue items={[
              [t("sources.wm"), s.incremental.watermark ? <code className="text-xs">{s.incremental.watermark}</code> : t("sources.notSet")],
              [t("sources.walk"), s.incremental.resume_pending ? <StatusBadge status="warning" label={t("sources.resume")} /> : <Badge tone="emerald">{t("common.none")}</Badge>],
            ]} />
            <p className="mt-3 text-xs leading-5 text-ink-muted">{t("sources.incrText")}{s.incremental.resume_pending && ` ${t("sources.incrPending")}`}</p>
          </div>
        </Card>
        <Card title={t("sources.esco")} subtitle={t("sources.escoSub")}>
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("sources.skillTypes")}</div>
              {data.esco.skill_types.map((x) => <div key={x.skill_type} className="flex justify-between gap-2 py-0.5 text-sm"><span>{skillType(x.skill_type)}</span><span className="tabular text-ink-muted">{int(x.n)}</span></div>)}
            </div>
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("sources.relTypes")}</div>
              {data.esco.relation_types.map((x) => <div key={x.relation_type} className="flex justify-between gap-2 py-0.5 text-sm"><span>{t(`roadmap.relation.${x.relation_type}`, { defaultValue: x.relation_type })}</span><span className="tabular text-ink-muted">{int(x.n)}</span></div>)}
            </div>
          </div>
          <div className="mt-5">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("sources.dict", { n: int(data.esco.dictionary_labels) })}</div>
            <div className="flex flex-wrap gap-1.5">{data.esco.dictionary_by_type.map((d) => <Badge key={d.label_type + d.lang}>{t(`labelType.${d.label_type}`, { defaultValue: d.label_type })} · {d.lang}: {int(d.n)}</Badge>)}</div>
            <p className="mt-3 text-xs leading-5 text-ink-muted">{t("sources.dictText")}</p>
          </div>
        </Card>
      </div>

      <Card title={t("sources.vacSources")} bodyClass="p-0">
        <TableWrap>
          <table className="w-full min-w-[820px]">
            <thead className="border-b border-slate-100"><tr><th className="th pl-5">{t("sources.colSource")}</th><th className="th text-right">{t("sources.colVac")}</th><th className="th text-right">{t("sources.colDup")}</th><th className="th text-right">{t("sources.colShare")}</th><th className="th text-right">{t("sources.colSalary")}</th><th className="th text-right">{t("sources.colText")}</th><th className="th text-right">{t("sources.colSkills")}</th><th className="th">{t("sources.colLatest")}</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {s.sources.map((r) => (
                <tr key={r.source}><td className="td pl-5 font-medium text-ink">{r.source_name}<div className="font-mono text-[11px] font-normal text-ink-faint">{r.source}</div></td>
                  <td className="td text-right tabular">{int(r.vacancies)}</td><td className="td text-right tabular">{int(r.duplicates_removed)}</td><td className="td text-right tabular">{pct(r.share_pct)}</td>
                  <td className="td text-right tabular">{int(r.with_salary)}</td><td className="td text-right tabular">{int(r.with_text)}</td><td className="td text-right tabular">{int(r.with_skills)}</td><td className="td">{dateTime(r.last_posted_at)}</td></tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title={t("sources.files")} subtitle={t("sources.filesSub")} bodyClass="p-0">
          <div className="max-h-[420px] overflow-y-auto">
            <TableWrap>
              <table className="w-full min-w-[560px]">
                <thead className="sticky top-0 border-b border-slate-100 bg-white"><tr><th className="th pl-5">{t("sources.colFile")}</th><th className="th">{t("sources.colKind")}</th><th className="th">{t("sources.colSnapshot")}</th><th className="th text-right">{t("sources.colRecords")}</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {s.files.map((f) => (
                    <tr key={f.file_id}><td className="td pl-5"><div className="max-w-[260px] truncate font-mono text-xs text-ink" title={f.path}>{f.path}</div><div className="font-mono text-[11px] text-ink-faint">sha256 {f.sha256}…</div></td>
                      <td className="td"><Badge>{kind(f.file_kind)}</Badge></td><td className="td text-xs">{dateTime(f.snapshot_at)}</td><td className="td text-right tabular">{int(f.record_count)}</td></tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </div>
        </Card>
        <Card title={t("sources.reqLog")} subtitle={t("sources.reqLogSub")} bodyClass="p-0">
          {s.requests.length === 0 ? <p className="p-5 text-sm text-ink-muted">{t("sources.noReq")}</p> : (
            <div className="max-h-[420px] overflow-y-auto">
              <TableWrap>
                <table className="w-full min-w-[560px]">
                  <thead className="sticky top-0 border-b border-slate-100 bg-white"><tr><th className="th pl-5">{t("sources.colTime")}</th><th className="th">{t("sources.colHttp")}</th><th className="th text-right">{t("sources.colRecords")}</th><th className="th text-right">{t("sources.colQuota")}</th><th className="th">{t("sources.colParams")}</th></tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {s.requests.map((r, i) => (
                      <tr key={i}><td className="td pl-5 text-xs">{dateTime(r.requested_at)}</td>
                        <td className="td"><StatusBadge status={r.status_code && r.status_code < 300 ? "success" : "failed"} label={String(r.status_code ?? "error")} /></td>
                        <td className="td text-right tabular">{int(r.records)}</td><td className="td text-right tabular text-xs">{r.quota_used ?? "—"}/{r.quota_limit ?? "—"}</td>
                        <td className="td break-all font-mono text-[11px] text-ink-muted">{Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(" ")}</td></tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </div>
          )}
        </Card>
      </div>

      <Card title={t("sources.dups", { n: s.mirrors.length })} subtitle={t("sources.dupsSub")}>
        <ul className="divide-y divide-slate-100">
          {s.mirrors.map((m) => (
            <li key={m.job_id} className="flex flex-col gap-1 py-2.5 text-sm sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0"><span className="font-medium text-ink">{m.title}</span> <span className="text-ink-muted">· {m.company_name}</span></div>
              <div className="flex shrink-0 flex-wrap gap-1.5 text-xs"><Badge tone="indigo">{t("sources.kept", { s: m.source_name })}</Badge>{m.also_listed_on.map((a) => <Badge key={a.job_id}>{t("sources.linked", { s: a.source })}</Badge>)}</div>
            </li>
          ))}
        </ul>
      </Card>
      <Note>{t("sources.privacy")}</Note>
    </div>
  );
}
