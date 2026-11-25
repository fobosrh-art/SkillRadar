import { Fragment, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Building2, CalendarDays, ExternalLink, Link2, MapPin, Wallet } from "lucide-react";
import { useApi } from "../lib/api";
import { Evidence, VacancyDetail } from "../lib/types";
import { date, employment, labelType, langName, salary } from "../lib/format";
import { Badge, Drawer, ErrorBox, Loading, Note } from "./ui";
import { useEscoLabels } from "../lib/labels";

/** Highlights evidence using the stored character offsets - exactly what the matcher found. */
export function Highlighted({ text, spans }: { text: string; spans: Evidence[] }) {
  const { tl } = useEscoLabels();
  const sorted = [...spans].sort((a, b) => a.start_pos - b.start_pos);
  const out: ReactNode[] = [];
  let pos = 0;
  sorted.forEach((s, i) => {
    if (s.start_pos < pos || s.end_pos > text.length) return;
    out.push(<Fragment key={`t${i}`}>{text.slice(pos, s.start_pos)}</Fragment>);
    out.push(<mark key={`m${i}`} className="ev" title={`${tl("skill", s.skill_uri, s.skill_label)} (ESCO: ${s.skill_label}) · ${labelType(s.label_type)}`}>{text.slice(s.start_pos, s.end_pos)}</mark>);
    pos = s.end_pos;
  });
  out.push(<Fragment key="end">{text.slice(pos)}</Fragment>);
  return <div className="whitespace-pre-line break-words text-sm leading-6 text-ink-soft">{out}</div>;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-6">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">{title}</h3>
      {children}
    </section>
  );
}

export function VacancyDrawer({ jobId, onClose }: { jobId: string | null; onClose: () => void }) {
  const { t } = useTranslation();
  const { tl } = useEscoLabels();
  const { data: v, error, loading } = useApi<VacancyDetail>(jobId ? `/api/vacancies/${encodeURIComponent(jobId)}` : null);
  const by = (f: string) => (v?.skills ?? []).filter((s) => s.field === f);
  const unique = v ? Array.from(new Map(v.skills.map((s) => [s.skill_uri, s])).values()) : [];
  const fieldName = (f: string) => t(`drawer.field.${f}`, { defaultValue: f });

  return (
    <Drawer open={!!jobId} onClose={onClose} wide
      title={v ? (
        <div className="min-w-0">
          <div className="truncate text-xs text-ink-muted">{v.source_name} · {v.job_id}</div>
          <h2 className="mt-0.5 break-words text-lg font-semibold leading-snug text-ink">{v.title}</h2>
        </div>
      ) : <span className="text-sm text-ink-muted">{t("drawer.vacancy")}</span>}>
      {loading && !v && <Loading label={t("drawer.loading")} />}
      {error && <ErrorBox message={error} />}
      {v && (
        <div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Info icon={<Building2 size={15} />} label={t("drawer.employer")} value={v.company_name ?? t("common.employerNotStated")} />
            <Info icon={<MapPin size={15} />} label={t("drawer.location")} value={v.city} />
            <Info icon={<Wallet size={15} />} label={t("drawer.salary")}
              value={v.has_salary ? `${salary(v.salary_from, v.salary_to, v.salary_currency, v.salary_period)}${v.salary_period ? "" : t("drawer.periodNote")}` : t("salary.notPublishedSource")} />
            <Info icon={<CalendarDays size={15} />} label={t("drawer.postedDeadline")} value={`${date(v.posted_at)} · ${v.deadline_at ? date(v.deadline_at) : t("drawer.noDeadline")}`} />
          </div>
          <div className="mt-4 flex flex-wrap gap-1.5">
            {v.employment_type && <Badge>{employment(v.employment_type)}</Badge>}
            {v.career_level_raw && <Badge title={t("drawer.sourceLabel")}>{v.career_level_raw}</Badge>}
            {v.job_function_raw && <Badge title={t("drawer.sourceCategory")}>{v.job_function_raw}</Badge>}
            {v.occupation_label && <Badge tone="indigo" title={t("drawer.escoOccTitle", { m: v.occupation_match })}>{t("drawer.escoOcc", { o: tl("occupation", v.occupation_uri, v.occupation_label) })}</Badge>}
            {v.text_lang && <Badge>{t("drawer.textLang", { l: langName(v.text_lang) })}</Badge>}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {v.url && <a className="btn-primary" href={v.url} target="_blank" rel="noopener noreferrer"><ExternalLink size={15} />{t("drawer.original")}</a>}
            {v.also_listed_on.map((m) => m.url && (
              <a key={m.job_id} className="btn-secondary" href={m.url} target="_blank" rel="noopener noreferrer" title={t("drawer.duplicate")}>
                <Link2 size={15} />{t("drawer.alsoOn", { s: m.source })}</a>
            ))}
          </div>

          <Section title={t("drawer.extracted", { n: unique.length })}>
            {unique.length === 0 ? (
              <p className="text-sm text-ink-muted">{v.has_text ? t("drawer.noMatch") : t("drawer.noText")}</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full min-w-[520px]">
                  <thead className="bg-slate-50"><tr><th className="th">{t("drawer.colSkill")}</th><th className="th">{t("drawer.colFound")}</th><th className="th">{t("drawer.colWhere")}</th><th className="th">{t("drawer.colType")}</th></tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {unique.map((u) => {
                      const ev = v.skills.filter((s) => s.skill_uri === u.skill_uri);
                      const forms = Array.from(ev.reduce((m, s) => m.set(s.matched_text, (m.get(s.matched_text) ?? 0) + 1), new Map<string, number>()));
                      return (
                        <tr key={u.skill_uri}>
                          <td className="td font-medium text-ink" title={`ESCO (EN): ${u.skill_label}`}>{tl("skill", u.skill_uri, u.skill_label)}</td>
                          <td className="td"><div className="flex flex-wrap gap-1">{forms.map(([txt, n]) => <span key={txt}><mark className="ev">{txt}</mark>{n > 1 && <span className="text-xs text-ink-muted"> ×{n}</span>}</span>)}</div></td>
                          <td className="td">{Array.from(new Set(ev.map((s) => fieldName(s.field)))).join(", ")}</td>
                          <td className="td text-xs">{Array.from(new Set(ev.map((s) => `${labelType(s.label_type)} · ${s.lang}`))).join("; ")}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title={t("drawer.description")}>
            {v.description_text ? <Highlighted text={v.description_text} spans={by("description")} />
              : <p className="text-sm text-ink-muted">{t("drawer.notPublished")}</p>}
          </Section>
          <Section title={t("drawer.requirements")}>
            {v.requirements_text ? <Highlighted text={v.requirements_text} spans={by("requirements")} />
              : <p className="text-sm text-ink-muted">{t("drawer.notPublished")}</p>}
          </Section>
          <div className="mt-6"><Note>{t("drawer.piiNote")}</Note></div>
        </div>
      )}
    </Drawer>
  );
}

function Info({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="flex gap-2.5 rounded-lg border border-slate-200 p-3">
      <span className="mt-0.5 text-ink-faint">{icon}</span>
      <div className="min-w-0"><div className="text-xs text-ink-muted">{label}</div><div className="break-words text-sm text-ink">{value}</div></div>
    </div>
  );
}
