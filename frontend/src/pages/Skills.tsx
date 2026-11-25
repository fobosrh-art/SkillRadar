import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";
import { qs, useApi, useDebounced } from "../lib/api";
import { Facets, SkillDetail, SkillsResponse } from "../lib/types";
import { int, labelType, langName, pct, skillType } from "../lib/format";
import { Badge, Card, Drawer, ErrorBox, Loading, Meter, Note, PageHeader, Segmented, Select, Stat, TableWrap } from "../components/ui";
import { RankBars, SegmentBar } from "../components/charts";
import { VacancyDrawer } from "../components/VacancyDrawer";
import { useEscoLabels } from "../lib/labels";


type SkillType = "" | "skill/competence" | "knowledge";

function Snippet({ snippet, matched }: { snippet: string; matched: string }) {
  const i = snippet.indexOf(matched);
  if (i < 0) return <span>{snippet}</span>;
  return <span>{snippet.slice(0, i)}<mark className="ev">{matched}</mark>{snippet.slice(i + matched.length)}</span>;
}

function SkillPanel({ uri, onClose, onJob }: { uri: string | null; onClose: () => void; onJob: (id: string) => void }) {
  const { t } = useTranslation();
  const { tl } = useEscoLabels();
  const { data: s, loading, error } = useApi<SkillDetail>(uri ? `/api/skill${qs({ uri })}` : null);
  return (
    <Drawer open={!!uri} onClose={onClose} wide title={s ? (
      <div><div className="text-xs text-ink-muted">{s.skill_type ? t("skills.panel.concept", { t: skillType(s.skill_type) }) : t("skills.panel.conceptGeneric")} · {t("common.escoEn")}</div>
        <h2 className="mt-0.5 text-lg font-semibold">{tl("skill", s.skill_uri, s.preferred_label)}</h2><div className="text-xs text-ink-faint">ESCO (EN): {s.preferred_label}</div></div>) : t("skills.panel.conceptGeneric")}>
      {loading && !s && <Loading />}
      {error && <ErrorBox message={error} />}
      {s && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Stat label={t("skills.panel.baku")} value={int(s.demand?.vacancies ?? 0)} />
            <Stat label={t("skills.panel.shareAn")} value={pct(s.demand?.share_of_text_pct ?? 0)} />
            <Stat label={t("skills.panel.escoOcc")} value={int((s.esco_occupations.essential ?? 0) + (s.esco_occupations.optional ?? 0))}
              sub={t("skills.panel.escoOccSub", { e: int(s.esco_occupations.essential ?? 0), o: int(s.esco_occupations.optional ?? 0) })} />
          </div>
          {s.description && <p className="text-sm leading-6 text-ink-soft" lang="en">{s.description}</p>}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("skills.panel.forms")}</h3>
            <div className="flex flex-wrap gap-1.5">
              {s.matched_forms.map((m) => (
                <span key={m.matched_text} className="chip bg-slate-100 text-ink-soft" title={`${labelType(m.label_type)} · ${m.lang}`}>
                  <mark className="ev">{m.matched_text}</mark><span className="tabular text-ink-muted">×{m.n}</span>
                </span>
              ))}
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("skills.panel.evidence", { n: s.evidence.length })}</h3>
            <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {s.evidence.map((e, i) => (
                <li key={i} className="p-3">
                  <button className="text-left text-sm font-medium text-ink hover:text-indigo-700" onClick={() => onJob(e.job_id)}>{e.title}</button>
                  <div className="text-xs text-ink-muted">{e.company_name ?? t("common.employerNotStated")} · {e.source_name} · {t("skills.panel.inField", { f: t(`drawer.field.${e.field}`, { defaultValue: e.field }) })} · {labelType(e.label_type)} ({e.lang})</div>
                  {e.snippet && <p className="mt-1.5 break-words text-sm leading-6 text-ink-soft"><Snippet snippet={e.snippet} matched={e.matched_text} /></p>}
                </li>
              ))}
            </ul>
          </div>
          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("skills.panel.with")}</h3>
              <ul className="space-y-1.5 text-sm">{s.co_occurring.map((c) => <li key={c.skill_uri} className="flex justify-between gap-2"><span>{tl("skill", c.skill_uri, c.skill_label)}</span><span className="tabular text-ink-muted">{int(c.vacancies)}</span></li>)}</ul>
            </div>
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("skills.panel.occs")}</h3>
              {s.market_occupations.length ? <ul className="space-y-1.5 text-sm">{s.market_occupations.map((c) => <li key={c.occupation_uri} className="flex justify-between gap-2"><span>{tl("occupation", c.occupation_uri, c.occupation_label)}</span><span className="tabular text-ink-muted">{int(c.vacancies)}</span></li>)}</ul>
                : <p className="text-sm text-ink-muted">{t("skills.panel.noOccs")}</p>}
            </div>
          </div>
          {s.alt_labels.length > 0 && <p className="text-xs leading-5 text-ink-muted">{t("skills.panel.alt", { l: s.alt_labels.join(" · ") })}</p>}
        </div>
      )}
    </Drawer>
  );
}

export default function Skills() {
  const { t } = useTranslation();
  const [sp, setSp] = useSearchParams();
  const occupation = sp.get("occupation") ?? "";
  const skill = sp.get("skill");
  const [type, setType] = useState<SkillType>("");
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 250);
  const [job, setJob] = useState<string | null>(null);
  const { tl } = useEscoLabels();
  const facets = useApi<Facets>("/api/vacancies/facets");
  const { data, error, loading, reload } = useApi<SkillsResponse>(`/api/skills${qs({ occupation, skill_type: type, q: dq })}`);
  const setParam = (k: string, v: string | null) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }); };
  const top = (data?.items ?? []).slice(0, 15).map((s) => ({ ...s, en: s.skill_label, skill_label: tl("skill", s.skill_uri, s.skill_label) }));
  const maxShare = data?.items[0]?.share_pct ?? 0;
  const occRaw = facets.data?.occupations.find((o) => o.value === occupation)?.label;
  const occLabel = occRaw ? tl("occupation", occupation, occRaw) : undefined;
  const evidenceTotal = data?.total_matches ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("skills.eyebrow")} title={t("skills.title")} description={t("skills.desc")} />
      <div className="card flex flex-col gap-3 p-4 md:flex-row md:items-end">
        <Select label={t("skills.occFilter")} value={occupation} onChange={(v) => setParam("occupation", v)} className="md:w-80">
          <option value="">{t("skills.allVac")}</option>
          {facets.data?.occupations.map((o) => <option key={o.value} value={o.value}>{tl("occupation", o.value, o.label)} ({int(o.n)})</option>)}
        </Select>
        <div>
          <span className="label">{t("skills.type")}</span>
          <Segmented<SkillType> value={type} onChange={setType} options={[{ value: "", label: t("common.all") }, { value: "skill/competence", label: t("skills.typeSkill") }, { value: "knowledge", label: t("skills.typeKnowledge") }]} />
        </div>
        <label className="block flex-1">
          <span className="label">{t("skills.find")}</span>
          <div className="relative"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input className="input pl-9" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("skills.findPh")} /></div>
        </label>
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label={occupation ? t("skills.kTotalOcc", { o: occLabel ?? "" }) : t("skills.kTotal")} value={int(data.coverage.total)} />
            <Stat label={t("skills.kAnalysable")} value={int(data.analysable_vacancies)} sub={t("skills.kAnalysableSub")} />
            <Stat label={t("skills.kDistinct")} value={int(data.total_skills)} sub={type || q || occupation ? t("skills.kDistinctFiltered") : t("skills.kDistinctSub")} />
            <Stat label={t("skills.kEvidence")} value={int(evidenceTotal)} sub={t("skills.kEvidenceSub")} />
          </div>
          <div className="grid gap-6 xl:grid-cols-5">
            <Card className="xl:col-span-3" title={`${t("skills.top", { n: top.length })}${occLabel ? ` · ${occLabel}` : ""}`} subtitle={t("skills.topSub")}>
              {top.length ? <RankBars data={top} label="skill_label" value="share_pct" valueSuffix="%" onClick={(d) => setParam("skill", d.skill_uri)}
                tooltip={(d) => [d.skill_label, [[t("skills.colVac"), int(d.vacancies)], [t("skills.colShare"), pct(d.share_pct)], [t("skills.mentions"), int(d.mentions)], ["ESCO (EN)", d.en]]]} />
                : <p className="py-10 text-center text-sm text-ink-muted">{t("skills.none")}</p>}
            </Card>
            <div className="min-w-0 space-y-6 xl:col-span-2">
              <Card title={t("skills.coverage")} subtitle={t("skills.coverageSub")}>
                <SegmentBar parts={[{ label: t("overview.found"), value: data.coverage.matched ?? 0 }, { label: t("overview.noMatch"), value: data.coverage.no_match ?? 0 }, { label: t("overview.noText"), value: data.coverage.no_text ?? 0, hint: t("overview.unknown") }]} />
              </Card>
              <Card title={t("skills.how")}>
                <div className="space-y-3">
                  {data.by_label_type.map((r) => (
                    <div key={r.label_type}><div className="mb-1 flex justify-between gap-2 text-xs"><span className="text-ink-soft">{labelType(r.label_type)}</span><span className="tabular text-ink-muted">{int(r.n)} ({pct((r.n / evidenceTotal) * 100, 0)})</span></div><Meter value={r.n} max={evidenceTotal} /></div>
                  ))}
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {data.by_language.map((l) => <Badge key={l.lang}>{t("skills.evidenceLang", { l: langName(l.lang), n: int(l.n) })}</Badge>)}
                  </div>
                </div>
              </Card>
            </div>
          </div>
          <Card title={t("skills.allN", { n: int(data.total_skills) })} subtitle={t("skills.shareDenom", { n: int(data.analysable_vacancies) })} bodyClass="p-0">
            <TableWrap>
              <table className="w-full min-w-[760px]">
                <thead className="border-b border-slate-100"><tr>
                  <th className="th pl-5">{t("skills.colRank")}</th><th className="th">{t("skills.colSkill")}</th><th className="th">{t("skills.colType")}</th><th className="th">{t("skills.colVac")}</th><th className="th w-48">{t("skills.colShare")}</th><th className="th">{t("skills.colLangs")}</th><th className="th">{t("skills.colVia")}</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((s, i) => (
                    <tr key={s.skill_uri} className="cursor-pointer hover:bg-slate-50" onClick={() => setParam("skill", s.skill_uri)}>
                      <td className="td pl-5 tabular text-ink-faint">{i + 1}</td>
                      <td className="td font-medium text-ink" title={`ESCO (EN): ${s.skill_label}`}>{tl("skill", s.skill_uri, s.skill_label)}</td>
                      <td className="td text-xs">{skillType(s.skill_type)}</td>
                      <td className="td tabular">{int(s.vacancies)}</td>
                      <td className="td"><div className="flex items-center gap-2"><Meter value={s.share_pct} max={maxShare} /><span className="w-14 text-right tabular text-xs">{pct(s.share_pct)}</span></div></td>
                      <td className="td text-xs">{(s.langs ?? "").split(",").map((l) => langName(l)).join(", ")}</td>
                      <td className="td text-xs">{(s.label_types ?? "").split(",").map((l) => labelType(l)).join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </Card>
          <Note title={t("skills.methodTitle")}>{t("skills.method")} {t("common.localLabelsNote")}</Note>
        </>
      )}
      <SkillPanel uri={skill} onClose={() => setParam("skill", null)} onJob={setJob} />
      <VacancyDrawer jobId={job} onClose={() => setJob(null)} />
    </div>
  );
}
