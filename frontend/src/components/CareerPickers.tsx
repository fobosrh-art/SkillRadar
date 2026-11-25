import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronDown, Plus, Search, X } from "lucide-react";
import { qs, useApi, useDebounced, useStored } from "../lib/api";
import { EscoOccupation, EscoSkill } from "../lib/types";
import { int, skillType } from "../lib/format";
import { cx } from "./ui";
import { useEscoLabels } from "../lib/labels";

export interface Picked { uri: string; label: string }
export interface CareerSelection { occupation: Picked | null; skills: Picked[] }

/** Shared between Career Match and Learning Roadmap; stored only in this browser. */
export function useCareerSelection() {
  const [sel, setSel] = useStored<CareerSelection>("skillradar.career.v1", { occupation: null, skills: [] });
  const has = (uri: string) => sel.skills.some((s) => s.uri === uri);
  const add = (p: Picked) => setSel((s) => (s.skills.some((x) => x.uri === p.uri) ? s : { ...s, skills: [...s.skills, p] }));
  const remove = (uri: string) => setSel((s) => ({ ...s, skills: s.skills.filter((x) => x.uri !== uri) }));
  const toggle = (p: Picked) => (has(p.uri) ? remove(p.uri) : add(p));
  const setOccupation = (o: Picked | null) => setSel((s) => ({ ...s, occupation: o }));
  const clear = () => setSel({ occupation: sel.occupation, skills: [] });
  return { sel, has, add, remove, toggle, setOccupation, clear };
}

function useOutside(ref: React.RefObject<HTMLElement>, cb: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) cb();
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, cb]);
}

export function OccupationPicker({ value, onChange }: { value: Picked | null; onChange: (p: Picked) => void }) {
  const { t } = useTranslation();
  const { tl } = useEscoLabels();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 250);
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, () => setOpen(false));
  const { data, loading } = useApi<EscoOccupation[]>(open ? `/api/esco/occupations${qs({ q: dq.length >= 2 ? dq : "", limit: 40 })}` : null);
  return (
    <div className="relative" ref={ref}>
      <button className="input flex items-center justify-between gap-2 text-left" onClick={() => setOpen((o) => !o)}>
        <span className={cx("truncate", value ? "text-ink" : "text-ink-faint")}>{value ? tl("occupation", value.uri, value.label) : t("picker.choose")}</span>
        <ChevronDown size={16} className="shrink-0 text-ink-faint" />
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-full rounded-xl border border-slate-200 bg-white shadow-xl">
          <div className="relative border-b border-slate-100 p-2">
            <Search size={15} className="absolute left-5 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input autoFocus className="input pl-9" placeholder={t("picker.search")} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="px-3 pt-2 text-[11px] font-medium uppercase tracking-wider text-ink-faint">
            {dq.length >= 2 ? t("picker.results") : t("picker.observed")}
          </div>
          <ul className="max-h-72 overflow-y-auto p-1">
            {loading && !data && <li className="px-3 py-2 text-sm text-ink-muted">{t("picker.searching")}</li>}
            {data?.map((o) => (
              <li key={o.occupation_uri}>
                <button className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50"
                  onClick={() => { onChange({ uri: o.occupation_uri, label: o.preferred_label }); setOpen(false); setQ(""); }}>
                  <span className="min-w-0 text-ink" title={`ESCO (EN): ${o.preferred_label}`}>{tl("occupation", o.occupation_uri, o.preferred_label)}</span>
                  <span className="shrink-0 text-xs text-ink-muted">{o.market_vacancies ? t("picker.bakuN", { n: int(o.market_vacancies) }) : t("picker.escoOnly")}</span>
                </button>
              </li>
            ))}
            {data?.length === 0 && <li className="px-3 py-2 text-sm text-ink-muted">{t("picker.noOcc")}</li>}
          </ul>
        </div>
      )}
    </div>
  );
}

export function SkillSearch({ onPick, has }: { onPick: (p: Picked) => void; has: (uri: string) => boolean }) {
  const { t } = useTranslation();
  const { tl } = useEscoLabels();
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 250);
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  useOutside(ref, () => setOpen(false));
  const { data } = useApi<EscoSkill[]>(dq.length >= 2 ? `/api/esco/skills${qs({ q: dq, limit: 20 })}` : null);
  return (
    <div className="relative" ref={ref}>
      <Search size={15} className="absolute left-3 top-[19px] -translate-y-1/2 text-ink-faint" />
      <input className="input pl-9" placeholder={t("picker.addSkill")} value={q}
        onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); }} />
      {open && dq.length >= 2 && data && (
        <ul className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-xl">
          {data.map((s) => (
            <li key={s.skill_uri}>
              <button className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50"
                onClick={() => { onPick({ uri: s.skill_uri, label: s.preferred_label }); setQ(""); setOpen(false); }}>
                <span className="flex min-w-0 items-center gap-2 text-ink">{has(s.skill_uri) ? <Check size={14} className="shrink-0 text-emerald-600" /> : <Plus size={14} className="shrink-0 text-ink-faint" />}<span title={`ESCO (EN): ${s.preferred_label}`}>{tl("skill", s.skill_uri, s.preferred_label)}</span></span>
                <span className="shrink-0 text-xs text-ink-muted">{s.baku_vacancies ? t("picker.bakuN", { n: int(s.baku_vacancies) }) : skillType(s.skill_type)}</span>
              </button>
            </li>
          ))}
          {data.length === 0 && <li className="px-3 py-2 text-sm text-ink-muted">{t("picker.noSkill", { q: dq })}</li>}
        </ul>
      )}
    </div>
  );
}

export function SkillChips({ skills, onRemove }: { skills: Picked[]; onRemove: (uri: string) => void }) {
  const { t } = useTranslation();
  const { tl } = useEscoLabels();
  if (!skills.length) return <p className="text-sm text-ink-muted">{t("picker.noneSelected")}</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {skills.map((s) => (
        <span key={s.uri} className="chip bg-indigo-50 py-1 text-indigo-800" title={`ESCO (EN): ${s.label}`}>
          {tl("skill", s.uri, s.label)}
          <button onClick={() => onRemove(s.uri)} aria-label={t("picker.remove", { s: s.label })} className="rounded hover:bg-indigo-100"><X size={12} /></button>
        </span>
      ))}
    </div>
  );
}

export function HaveToggle({ has, onClick }: { has: boolean; onClick: () => void }) {
  const { t } = useTranslation();
  return (
    <button onClick={onClick} title={has ? t("career.have") : t("career.mark")} aria-pressed={has}
      className={cx("inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border transition",
        has ? "border-emerald-600 bg-emerald-600 text-white" : "border-slate-300 bg-white text-transparent hover:border-indigo-400")}>
      <Check size={14} />
    </button>
  );
}
