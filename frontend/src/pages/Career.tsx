import { ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Building2, CheckCircle2, CircleDashed, GraduationCap, Target } from "lucide-react";
import { api, useDebounced } from "../lib/api";
import { CareerMatch, EscoReq, MarketReq } from "../lib/types";
import { int, pct } from "../lib/format";
import { Badge, Card, Empty, ErrorBox, Loading, Meter, Note, PageHeader } from "../components/ui";
import { HaveToggle, OccupationPicker, SkillChips, SkillSearch, useCareerSelection } from "../components/CareerPickers";
import { useEscoLabels } from "../lib/labels";
import { CompareOccupations, MatchingJobs } from "../components/CareerExtras";


/** Below this many mapped vacancies, market percentages are flagged as anecdotal. */
export const MIN_MARKET_SAMPLE = 5;

function Score({ title, value, sub, icon, sample }: { title: string; value: number | null; sub: string; icon: ReactNode; sample?: ReactNode }) {
  return (
    <div className="card flex flex-col p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium text-ink-muted">{icon}{title}</div>
        {sample}
      </div>
      <div className="mt-2 text-3xl font-semibold tracking-tight tabular">{value === null ? "—" : pct(value, 0)}</div>
      <Meter value={value ?? 0} className="mt-3" />
      <div className="mt-2 text-xs leading-5 text-ink-muted">{sub}</div>
    </div>
  );
}

function ReqRow({ label, has, onToggle, right, sub }: { label: string; has: boolean; onToggle: () => void; right?: ReactNode; sub?: ReactNode }) {
  return (
    <li className="flex items-center gap-3 py-2.5">
      <HaveToggle has={has} onClick={onToggle} />
      <div className="min-w-0 flex-1">
        <div className={has ? "text-sm font-medium text-ink" : "text-sm text-ink-soft"}>{label}</div>
        {sub && <div className="text-xs text-ink-muted">{sub}</div>}
      </div>
      {right}
    </li>
  );
}

export default function Career() {
  const { t } = useTranslation();
  const c = useCareerSelection();
  const { tl } = useEscoLabels();
  const [res, setRes] = useState<CareerMatch | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showAllOptional, setShowAllOptional] = useState(false);
  const key = useDebounced(JSON.stringify([c.sel.occupation?.uri, c.sel.skills.map((s) => s.uri)]), 250);

  useEffect(() => {
    if (!c.sel.occupation) {
      setRes(null);
      return;
    }
    setBusy(true);
    api.post<CareerMatch>("/api/career/match", { occupation_uri: c.sel.occupation.uri, skill_uris: c.sel.skills.map((s) => s.uri) })
      .then((r) => { setRes(r); setErr(null); }).catch((e: Error) => setErr(e.message)).finally(() => setBusy(false));
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (r: MarketReq | EscoReq) => c.toggle({ uri: r.skill_uri, label: r.label });
  const optional = res ? (showAllOptional ? res.esco_optional : res.esco_optional.slice(0, 12)) : [];
  const n = res?.occupation_vacancies ?? 0;
  const small = !!res && n > 0 && n < MIN_MARKET_SAMPLE;
  const rel = (r: string | null) => (r ? t(`roadmap.relation.${r}`, { defaultValue: r }) : "");

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("career.eyebrow")} title={t("career.title")} description={t("career.desc")} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <Card title={t("career.step1")} className="h-fit">
          <OccupationPicker value={c.sel.occupation} onChange={c.setOccupation} />
          <p className="mt-3 text-xs leading-5 text-ink-muted">{t("career.step1Hint")}</p>
        </Card>
        <Card title={t("career.step2", { n: c.sel.skills.length })} actions={c.sel.skills.length > 0 && <button className="btn-ghost px-2 text-xs" onClick={c.clear}>{t("common.clearAll")}</button>}>
          <SkillSearch onPick={c.add} has={c.has} />
          <div className="mt-3"><SkillChips skills={c.sel.skills} onRemove={c.remove} /></div>
        </Card>
      </div>

      {!c.sel.occupation && <div className="card"><Empty title={t("career.start")} icon={<Target size={28} />}>{t("career.startHint")}</Empty></div>}
      {err && <ErrorBox message={err} />}
      {c.sel.occupation && busy && !res && <Loading label={t("career.comparing")} />}

      {res && (
        <div className={busy ? "space-y-6 opacity-70 transition" : "space-y-6 transition"}>
          {small && <Note tone="warn" title={t("career.insufficientTitle")}>{t("career.insufficient", { n, min: MIN_MARKET_SAMPLE })}</Note>}
          <div className="grid gap-3 md:grid-cols-3">
            <Score title={t("career.sMarket")} icon={<Building2 size={14} />} value={res.coverage.market.weighted_pct}
              sample={<Badge tone={n === 0 ? "slate" : small ? "amber" : "indigo"}>{n ? t("career.sample", { n }) : t("career.sampleNone")}</Badge>}
              sub={n ? t("career.sMarketSub", { m: res.coverage.market.matched, t: res.coverage.market.total, n }) : t("career.sMarketNone")} />
            <Score title={t("career.sEss")} icon={<GraduationCap size={14} />} value={res.coverage.esco_essential.pct}
              sub={t("career.sEssSub", { m: res.coverage.esco_essential.matched, t: res.coverage.esco_essential.total })} />
            <Score title={t("career.sOpt")} icon={<CircleDashed size={14} />} value={res.coverage.esco_optional.pct}
              sub={t("career.sOptSub", { m: res.coverage.esco_optional.matched, t: res.coverage.esco_optional.total })} />
          </div>
          <p className="text-xs text-ink-muted">{t("career.notProbability")}</p>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card title={t("career.market")} subtitle={n ? t("career.marketSub", { n, o: tl("occupation", res.occupation.occupation_uri, res.occupation.preferred_label) }) : t("career.marketSubNone")}
              actions={<Badge tone={n === 0 ? "slate" : small ? "amber" : "indigo"}>n = {n}</Badge>}>
              {res.market_requirements.length === 0 ? (
                <Empty title={t("career.noMarket")}>{n ? t("career.noMarketText") : t("career.noMarketNoVac")}</Empty>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {res.market_requirements.map((r) => (
                    <ReqRow key={r.skill_uri} label={tl("skill", r.skill_uri, r.label)} has={r.user_has} onToggle={() => toggle(r)}
                      sub={r.esco_relation ? t("career.alsoEsco", { r: rel(r.esco_relation) }) : t("career.notEsco")}
                      right={<div className="w-36 shrink-0"><div className="mb-1 text-right text-xs tabular text-ink-muted">{t("career.ofN", { v: r.vacancies, n, p: pct(r.share_pct, 0) })}</div><Meter value={r.share_pct} /></div>} />
                  ))}
                </ul>
              )}
            </Card>
            <Card title={t("career.ess")} subtitle={t("career.essSub")}>
              {res.esco_essential.length === 0 ? <p className="text-sm text-ink-muted">{t("career.essNone")}</p> : (
                <ul className="divide-y divide-slate-100">
                  {res.esco_essential.map((r) => (
                    <ReqRow key={r.skill_uri} label={tl("skill", r.skill_uri, r.label)} has={r.user_has} onToggle={() => toggle(r)}
                      sub={r.skill_type ? t(`skillType.${r.skill_type}`, { defaultValue: r.skill_type }) : undefined}
                      right={r.baku.vacancies ? <Badge tone="indigo">{t("career.bakuN", { n: int(r.baku.vacancies) })}</Badge> : <span className="shrink-0 text-xs text-ink-faint">{t("career.noBaku")}</span>} />
                  ))}
                </ul>
              )}
            </Card>
          </div>

          {c.sel.occupation && <MatchingJobs occupation={c.sel.occupation} skills={c.sel.skills} />}
          {c.sel.occupation && <CompareOccupations occupation={c.sel.occupation} skills={c.sel.skills} />}

          <Card title={t("career.opt", { n: res.esco_optional.length })} subtitle={t("career.optSub")}>
            <ul className="grid gap-x-8 divide-y divide-slate-100 md:grid-cols-2 md:divide-y-0">
              {optional.map((r) => (
                <ReqRow key={r.skill_uri} label={tl("skill", r.skill_uri, r.label)} has={r.user_has} onToggle={() => toggle(r)}
                  right={r.baku.vacancies ? <Badge tone="indigo">{t("career.bakuShort", { n: int(r.baku.vacancies) })}</Badge> : undefined} />
              ))}
            </ul>
            {res.esco_optional.length > 12 && (
              <button className="btn-ghost mt-2 text-xs" onClick={() => setShowAllOptional((s) => !s)}>
                {showAllOptional ? t("common.showFewer") : t("common.showAll", { n: res.esco_optional.length })}
              </button>
            )}
          </Card>

          {res.other_user_skills.length > 0 && (
            <Card title={t("career.other")} subtitle={t("career.otherSub")}>
              <div className="flex flex-wrap gap-1.5">{res.other_user_skills.map((s) => <Badge key={s.skill_uri}><CheckCircle2 size={12} />{tl("skill", s.skill_uri, s.label)}</Badge>)}</div>
            </Card>
          )}

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <Note title={t("career.howTitle")}>
              {t("career.how")}
              <ul className="mt-1 list-disc pl-5">
                <li>{n ? t("career.lim1", { n }) : t("career.lim1none")}</li>
                <li>{t("career.lim2")}</li>
                <li>{t("common.localLabelsNote")}</li>
              </ul>
            </Note>
            <Link to="/roadmap" className="btn-primary justify-self-start">{t("career.build")} <ArrowRight size={15} /></Link>
          </div>
          <p className="text-xs text-ink-muted">{t("career.isco", { g: res.occupation.isco_group ?? "—", n: int(res.esco_essential.length + res.esco_optional.length) })}</p>
        </div>
      )}
    </div>
  );
}
