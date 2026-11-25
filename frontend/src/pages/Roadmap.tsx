import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, ChevronDown, ChevronUp, Download, Route, UserPlus } from "lucide-react";
import { api, useStored } from "../lib/api";
import { Roadmap as RoadmapT, RoadmapItem } from "../lib/types";
import { int, num } from "../lib/format";
import { Badge, Card, Empty, ErrorBox, Loading, Meter, Note, PageHeader, Segmented, cx } from "../components/ui";
import { C } from "../components/charts";
import { HaveToggle, OccupationPicker, useCareerSelection } from "../components/CareerPickers";
import { MIN_MARKET_SAMPLE } from "./Career";
import { useEscoLabels } from "../lib/labels";


const COMP: { key: keyof RoadmapItem["components"]; label: string }[] = [
  { key: "occupation_market", label: "roadmap.cOcc" },
  { key: "esco_relation", label: "roadmap.cEsco" },
  { key: "baku_market", label: "roadmap.cBaku" },
];

function ScoreBar({ item }: { item: RoadmapItem }) {
  const { t } = useTranslation();
  return (
    <div>
      <div className="flex h-2 w-full gap-0.5 overflow-hidden rounded-full bg-slate-100">
        {COMP.map((c, i) => item.components[c.key] > 0 && (
          <div key={c.key} style={{ width: `${item.components[c.key]}%`, background: C.ordinal[i] }} title={`${t(c.label)}: ${num(item.components[c.key], 1)}`} />
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-ink-muted">
        {COMP.map((c, i) => (
          <span key={c.key} className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm" style={{ background: C.ordinal[i] }} />{t(c.label)} <span className="tabular font-medium text-ink-soft">{num(item.components[c.key], 1)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export default function Roadmap() {
  const { t } = useTranslation();
  const c = useCareerSelection();
  const { tl } = useEscoLabels();
  const occ = c.sel.occupation;
  const [data, setData] = useState<RoadmapT | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useStored<Record<string, string[]>>("skillradar.roadmap.progress.v1", {});
  const [view, setView] = useState<"all" | "open" | "done">("all");
  const [openDesc, setOpenDesc] = useState<string | null>(null);
  const skillKey = c.sel.skills.map((s) => s.uri).join("|");

  useEffect(() => {
    if (!occ) return;
    setBusy(true);
    api.post<RoadmapT>("/api/career/roadmap", { occupation_uri: occ.uri, skill_uris: c.sel.skills.map((s) => s.uri) })
      .then((r) => { setData(r); setErr(null); }).catch((e: Error) => setErr(e.message)).finally(() => setBusy(false));
  }, [occ?.uri, skillKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const completed = useMemo(() => new Set(occ ? done[occ.uri] ?? [] : []), [done, occ]);
  const toggleDone = (uri: string) => {
    if (!occ) return;
    setDone((d) => {
      const cur = new Set(d[occ.uri] ?? []);
      if (cur.has(uri)) cur.delete(uri); else cur.add(uri);
      return { ...d, [occ.uri]: [...cur] };
    });
  };
  const items = data?.items ?? [];
  const nDone = items.filter((i) => completed.has(i.skill_uri)).length;
  const visible = useMemo(() => items.filter((i) => view === "all" || (view === "done") === completed.has(i.skill_uri)), [items, view, completed]);
  const moveDoneToSkills = () => {
    items.filter((i) => completed.has(i.skill_uri)).forEach((i) => c.add({ uri: i.skill_uri, label: i.label }));
    if (occ) setDone((d) => ({ ...d, [occ.uri]: [] }));
  };
  const rel = (r: string) => t(`roadmap.relation.${r}`, { defaultValue: r });
  const reasons = (i: RoadmapItem) => [
    i.occupation_vacancies > 0 && data ? t("roadmap.rOcc", { v: i.occupation_vacancies, n: data.occupation_vacancies }) : null,
    i.esco_relation ? t("roadmap.rEsco", { r: rel(i.esco_relation) }) : null,
    i.baku_vacancies > 0 ? t("roadmap.rBaku", { n: int(i.baku_vacancies) }) : null,
  ].filter(Boolean).join(" · ");
  const tiers = { high: [t("roadmap.high"), t("roadmap.highHint"), "indigo"], medium: [t("roadmap.medium"), t("roadmap.mediumHint"), "slate"], low: [t("roadmap.low"), t("roadmap.lowHint"), "slate"] } as const;
  const n = data?.occupation_vacancies ?? 0;
  /** CSV of the personal plan (UTF-8 with BOM so Excel shows Cyrillic and Azerbaijani letters). No personal data. */
  const exportCsv = () => {
    if (!data || !occ) return;
    const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
    const head = [t("roadmap.csv.skill"), "ESCO (EN)", t("roadmap.csv.priority"), t("roadmap.csv.score"), t("roadmap.csv.occVac"),
      t("roadmap.csv.bakuVac"), t("roadmap.csv.esco"), t("roadmap.csv.reason"), t("roadmap.csv.status")];
    const lines = items.map((i) => [tl("skill", i.skill_uri, i.label), i.label, t(`roadmap.${i.priority}`), i.score, i.occupation_vacancies,
      i.baku_vacancies, i.esco_relation ? rel(i.esco_relation) : "", reasons(i), completed.has(i.skill_uri) ? t("roadmap.vDone") : t("roadmap.vOpen")].map(esc).join(";"));
    const csv = "\uFEFF" + [head.map(esc).join(";"), ...lines].join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = `skillradar-roadmap-${occ.label.replace(/[^a-z0-9]+/gi, "-")}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("roadmap.eyebrow")} title={t("roadmap.title")} description={t("roadmap.desc")} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <Card title={t("roadmap.target")} className="h-fit">
          <OccupationPicker value={occ} onChange={c.setOccupation} />
          <p className="mt-3 text-xs text-ink-muted">{t("roadmap.selected", { n: c.sel.skills.length })} <Link className="font-medium text-indigo-700" to="/career">{t("roadmap.edit")}</Link>.</p>
        </Card>
        {data && (
          <Card title={t("roadmap.progress")} subtitle={t("roadmap.progressSub")}>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="text-3xl font-semibold tabular">{nDone}<span className="text-lg text-ink-muted"> / {items.length}</span></div>
              <Segmented value={view} onChange={setView} options={[{ value: "all", label: t("roadmap.vAll") }, { value: "open", label: t("roadmap.vOpen") }, { value: "done", label: t("roadmap.vDone") }]} />
            </div>
            <Meter value={nDone} max={items.length || 1} className="mt-3 h-2" />
            <button className="btn-secondary mr-2 mt-4 text-xs" onClick={exportCsv}><Download size={14} />{t("roadmap.export")}</button>
            {nDone > 0 && <button className="btn-secondary mt-4 text-xs" onClick={moveDoneToSkills}><UserPlus size={14} />{t("roadmap.addDone", { n: nDone })}</button>}
          </Card>
        )}
      </div>

      {!occ && <div className="card"><Empty title={t("roadmap.choose")} icon={<Route size={28} />}>{t("roadmap.chooseHint")}</Empty></div>}
      {err && <ErrorBox message={err} />}
      {occ && busy && !data && <Loading label={t("roadmap.prioritising")} />}

      {data && (
        <>
          {n > 0 && n < MIN_MARKET_SAMPLE && <Note tone="warn" title={t("career.insufficientTitle")}>{t("career.insufficient", { n, min: MIN_MARKET_SAMPLE })}</Note>}
          {items.length === 0 ? (
            <div className="card"><Empty title={t("roadmap.nothing")}>{t("roadmap.nothingText", { o: tl("occupation", data.occupation.occupation_uri, data.occupation.preferred_label) })}</Empty></div>
          ) : (["high", "medium", "low"] as const).map((tier) => {
            const list = visible.filter((i) => i.priority === tier);
            if (!list.length) return null;
            const [label, hint, tone] = tiers[tier];
            return (
              <Card key={tier} title={<span className="inline-flex items-center gap-2">{label}<Badge tone={tone}>{list.length}</Badge></span>} subtitle={hint}>
                <ul className="divide-y divide-slate-100">
                  {list.map((i) => {
                    const isDone = completed.has(i.skill_uri);
                    return (
                      <li key={i.skill_uri} className="py-4 first:pt-0 last:pb-0">
                        <div className="flex gap-3">
                          <HaveToggle has={isDone} onClick={() => toggleDone(i.skill_uri)} />
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className={cx("font-medium", isDone ? "text-ink-muted line-through" : "text-ink")} title={`ESCO (EN): ${i.label}`}>{tl("skill", i.skill_uri, i.label)}</span>
                              {i.esco_relation && <Badge tone={i.esco_relation === "essential" ? "indigo" : "slate"}>{t("roadmap.escoRel", { r: rel(i.esco_relation) })}</Badge>}
                              {i.occupation_vacancies > 0 && <Badge tone="emerald">{t("roadmap.seenIn", { n: i.occupation_vacancies })}</Badge>}
                              <span className="ml-auto text-sm font-semibold tabular text-ink">{num(i.score, 1)}<span className="text-xs font-normal text-ink-muted"> / 100</span></span>
                            </div>
                            <p className="mt-1 text-xs text-ink-muted">{reasons(i)}</p>
                            <div className="mt-2.5"><ScoreBar item={i} /></div>
                            {i.description && (
                              <button className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-indigo-700" onClick={() => setOpenDesc(openDesc === i.skill_uri ? null : i.skill_uri)}>
                                {openDesc === i.skill_uri ? <ChevronUp size={13} /> : <ChevronDown size={13} />}{t("roadmap.covers")}
                              </button>
                            )}
                            {openDesc === i.skill_uri && <p className="mt-1.5 text-sm leading-6 text-ink-soft" lang="en">{i.description}</p>}
                            {i.baku_vacancies > 0 && <Link to={`/skills?skill=${encodeURIComponent(i.skill_uri)}`} className="ml-3 inline-flex items-center gap-1 text-xs font-medium text-indigo-700">{t("roadmap.evidence")} <ArrowRight size={12} /></Link>}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </Card>
            );
          })}
          <Note title={t("roadmap.formula")}>
            <ul className="list-disc pl-5">
              {["fOcc", "fEsco", "fBaku", "fTiers"].map((k) => <li key={k}>{t(`roadmap.${k}`)}</li>)}
            </ul>
            <div className="mt-1">
              {t("roadmap.basis", { n: int(n), o: tl("occupation", data.occupation.occupation_uri, data.occupation.preferred_label) })}
              {data.omitted_optional_without_evidence > 0 && ` ${t("roadmap.omitted", { n: data.omitted_optional_without_evidence })}`}
              {" "}{t("roadmap.checklistNote")}
            </div>
          </Note>
        </>
      )}
    </div>
  );
}
