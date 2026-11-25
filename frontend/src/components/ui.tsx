import { ReactNode, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Info, Loader2, MinusCircle, X, XCircle } from "lucide-react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function PageHeader({ title, description, actions, eyebrow }: {
  title: string; description?: ReactNode; actions?: ReactNode; eyebrow?: string;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-indigo-600">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1.5 max-w-3xl text-sm leading-6 text-ink-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, subtitle, actions, children, className, bodyClass }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={cx("card min-w-0", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs leading-5 text-ink-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("p-5", bodyClass)}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, icon, tone = "default" }: {
  label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode; tone?: "default" | "good" | "bad";
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-ink-muted">{label}</span>
        {icon && <span className="text-ink-faint">{icon}</span>}
      </div>
      <div className={cx("mt-2 text-2xl font-semibold tracking-tight tabular",
        tone === "good" && "text-emerald-700", tone === "bad" && "text-rose-700")}>{value}</div>
      {sub && <div className="mt-1 text-xs leading-5 text-ink-muted">{sub}</div>}
    </div>
  );
}

const STATUS: Record<string, { cls: string; icon: ReactNode }> = {
  success: { cls: "bg-emerald-50 text-emerald-800 ring-emerald-200", icon: <CheckCircle2 size={13} /> },
  pass: { cls: "bg-emerald-50 text-emerald-800 ring-emerald-200", icon: <CheckCircle2 size={13} /> },
  blocked: { cls: "bg-amber-50 text-amber-800 ring-amber-200", icon: <AlertTriangle size={13} /> },
  warning: { cls: "bg-amber-50 text-amber-800 ring-amber-200", icon: <AlertTriangle size={13} /> },
  warn: { cls: "bg-amber-50 text-amber-800 ring-amber-200", icon: <AlertTriangle size={13} /> },
  skipped_busy: { cls: "bg-amber-50 text-amber-800 ring-amber-200", icon: <AlertTriangle size={13} /> },
  failed: { cls: "bg-rose-50 text-rose-800 ring-rose-200", icon: <XCircle size={13} /> },
  fail: { cls: "bg-rose-50 text-rose-800 ring-rose-200", icon: <XCircle size={13} /> },
  error: { cls: "bg-rose-50 text-rose-800 ring-rose-200", icon: <XCircle size={13} /> },
  skipped: { cls: "bg-slate-100 text-slate-700 ring-slate-200", icon: <MinusCircle size={13} /> },
  running: { cls: "bg-indigo-50 text-indigo-800 ring-indigo-200", icon: <Loader2 size={13} className="animate-spin" /> },
  queued: { cls: "bg-indigo-50 text-indigo-800 ring-indigo-200", icon: <Loader2 size={13} className="animate-spin" /> },
};

/** Status is always icon + text, never colour alone. */
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const { t } = useTranslation();
  const s = STATUS[status] ?? { cls: "bg-slate-100 text-slate-700 ring-slate-200", icon: <Info size={13} /> };
  return <span className={cx("chip ring-1 ring-inset", s.cls)}>{s.icon}{label ?? t(`status.${status}`, { defaultValue: status })}</span>;
}

export function Badge({ children, tone = "slate", title }: { children: ReactNode; tone?: "slate" | "indigo" | "amber" | "emerald" | "rose"; title?: string }) {
  const t = {
    slate: "bg-slate-100 text-slate-700", indigo: "bg-indigo-50 text-indigo-700", amber: "bg-amber-50 text-amber-800",
    emerald: "bg-emerald-50 text-emerald-800", rose: "bg-rose-50 text-rose-800",
  }[tone];
  return <span title={title} className={cx("chip", t)}>{children}</span>;
}

export function Loading({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-ink-muted">
      <Loader2 size={16} className="animate-spin text-indigo-600" />{label ?? t("common.loading")}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
      <XCircle size={18} className="mt-0.5 shrink-0" />
      <div className="flex-1">
        <div className="font-medium">{t("common.loadError")}</div>
        <div className="mt-0.5 text-rose-800">{message}</div>
      </div>
      {onRetry && <button className="btn-secondary" onClick={onRetry}>{t("common.retry")}</button>}
    </div>
  );
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {icon && <div className="mb-3 text-ink-faint">{icon}</div>}
      <div className="text-sm font-medium text-ink">{title}</div>
      {children && <div className="mt-1 max-w-md text-sm text-ink-muted">{children}</div>}
    </div>
  );
}

export function Note({ children, tone = "info", title }: { children: ReactNode; tone?: "info" | "warn"; title?: string }) {
  return (
    <div className={cx("flex gap-3 rounded-xl border p-4 text-sm leading-6",
      tone === "info" ? "border-indigo-100 bg-indigo-50/60 text-indigo-950" : "border-amber-200 bg-amber-50 text-amber-950")}>
      {tone === "info" ? <Info size={17} className="mt-1 shrink-0 text-indigo-600" /> : <AlertTriangle size={17} className="mt-1 shrink-0 text-amber-600" />}
      <div>{title && <div className="font-medium">{title}</div>}{children}</div>
    </div>
  );
}

export function Meter({ value, max = 100, className }: { value: number; max?: number; className?: string }) {
  const w = max ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div className={cx("h-1.5 w-full overflow-hidden rounded-full bg-slate-100", className)}>
      <div className="h-full rounded-full bg-indigo-600" style={{ width: `${w}%` }} />
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange }: {
  options: { value: T; label: string }[]; value: T; onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5">
      {options.map((o) => (
        <button key={o.value} onClick={() => onChange(o.value)}
          className={cx("rounded-md px-3 py-1.5 text-xs font-medium transition",
            value === o.value ? "bg-white text-ink shadow-sm" : "text-ink-muted hover:text-ink")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const { t } = useTranslation();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="flex items-center justify-between gap-3 text-sm text-ink-muted">
      <span className="tabular">{t("common.rangeOf", { from, to, total })}</span>
      <div className="flex items-center gap-1">
        <button className="btn-ghost px-2" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label={t("common.previous")}><ChevronLeft size={16} /></button>
        <span className="tabular px-2">{t("common.pageOf", { page, pages })}</span>
        <button className="btn-ghost px-2" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label={t("common.next")}><ChevronRight size={16} /></button>
      </div>
    </div>
  );
}

export function Drawer({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  const { t } = useTranslation();
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30" onClick={onClose} />
      <aside className={cx("relative flex h-full w-full flex-col bg-white shadow-2xl", wide ? "max-w-3xl" : "max-w-xl")}>
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-6 py-4">
          <div className="min-w-0 flex-1">{title}</div>
          <button className="btn-ghost -mr-2 px-2" onClick={onClose} aria-label={t("common.close")}><X size={18} /></button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </aside>
    </div>
  );
}

export function Dialog({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer: ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div role="dialog" aria-modal="true" className="relative w-full max-w-lg rounded-2xl bg-white shadow-2xl">
        <div className="border-b border-slate-100 px-6 py-4 text-base font-semibold">{title}</div>
        <div className="px-6 py-5 text-sm leading-6 text-ink-soft">{children}</div>
        <div className="flex justify-end gap-2 border-t border-slate-100 px-6 py-4">{footer}</div>
      </div>
    </div>
  );
}

export function Select({ value, onChange, children, className, label }: {
  value: string; onChange: (v: string) => void; children: ReactNode; className?: string; label?: string;
}) {
  return (
    <label className={cx("block", className)}>
      {label && <span className="label">{label}</span>}
      <select className="input pr-8" value={value} onChange={(e) => onChange(e.target.value)}>{children}</select>
    </label>
  );
}

export function KeyValue({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map(([k, v], i) => (
        <div key={i} className="min-w-0">
          <dt className="text-xs text-ink-muted">{k}</dt>
          <dd className="mt-0.5 break-words text-sm text-ink">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Wraps a wide table so the page itself never scrolls horizontally. */
export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="max-w-full overflow-x-auto">{children}</div>;
}
