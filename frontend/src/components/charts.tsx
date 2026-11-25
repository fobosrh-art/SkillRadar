import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ReactNode } from "react";
import { num } from "../lib/format";

// Validated with the dataviz palette validator (light surface #ffffff):
//   primary series #4f46e5 passes contrast >= 3:1; ordinal ramp below passes all ordinal checks.
export const C = {
  primary: "#4f46e5",
  ordinal: ["#312e81", "#4f46e5", "#818cf8"],
  grid: "#eef2f7",
  axis: "#64748b",
  good: "#0ca30c",
  warning: "#fab219",
  critical: "#d03b3b",
  neutral: "#94a3b8",
};

const tick = { fill: C.axis, fontSize: 12 };

export function TooltipBox({ title, rows }: { title: ReactNode; rows: [ReactNode, ReactNode][] }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 max-w-[260px] font-medium text-ink">{title}</div>
      {rows.map(([k, v], i) => (
        <div key={i} className="flex justify-between gap-4 text-ink-muted">
          <span>{k}</span><span className="tabular font-medium text-ink">{v}</span>
        </div>
      ))}
    </div>
  );
}

/** Horizontal ranked bars, one series. Labels on the axis, value on hover + optional end label. */
export function RankBars<T extends object>({ data, label, value, height, tooltip, onClick, valueSuffix = "", maxLabel = 34 }: {
  data: T[]; label: keyof T; value: keyof T; height?: number; tooltip: (d: T) => [ReactNode, [ReactNode, ReactNode][]];
  onClick?: (d: T) => void; valueSuffix?: string; maxLabel?: number;
}) {
  const h = height ?? Math.max(160, data.length * 30 + 24);
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 44, bottom: 4, left: 4 }} barCategoryGap={6}>
        <CartesianGrid horizontal={false} stroke={C.grid} />
        <XAxis type="number" tick={tick} axisLine={false} tickLine={false} allowDecimals={false}
          tickFormatter={(v) => `${num(v)}${valueSuffix}`} />
        <YAxis type="category" dataKey={label as string} width={Math.min(240, maxLabel * 7)} tick={tick} axisLine={false}
          tickLine={false} interval={0}
          tickFormatter={(v: string) => (v.length > maxLabel ? `${v.slice(0, maxLabel - 1)}…` : v)} />
        <Tooltip cursor={{ fill: "rgba(79,70,229,0.06)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const [t, rows] = tooltip(payload[0].payload as T);
            return <TooltipBox title={t} rows={rows} />;
          }} />
        <Bar dataKey={value as string} fill={C.primary} radius={[0, 4, 4, 0]} maxBarSize={18}
          label={{ position: "right", fill: C.axis, fontSize: 11, formatter: (v: number) => `${num(v, 1)}${valueSuffix}` }}
          onClick={onClick ? (d: unknown) => onClick((d as { payload: T }).payload) : undefined} cursor={onClick ? "pointer" : undefined} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Vertical columns (time or bins), one series, optional per-bar colour (used for status, with legend). */
export function Columns<T extends object>({ data, x, y, height = 240, tooltip, xFormat, colorOf, yLabel }: {
  data: T[]; x: keyof T; y: keyof T; height?: number; tooltip: (d: T) => [ReactNode, [ReactNode, ReactNode][]];
  xFormat?: (v: string) => string; colorOf?: (d: T) => string; yLabel?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: yLabel ? 8 : -12 }} barCategoryGap="18%">
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey={x as string} tick={tick} axisLine={{ stroke: "#cbd5e1" }} tickLine={false}
          tickFormatter={xFormat} minTickGap={8} />
        <YAxis tick={tick} axisLine={false} tickLine={false} allowDecimals={false}
          label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fill: C.axis, fontSize: 11, dx: 4 } : undefined} />
        <Tooltip cursor={{ fill: "rgba(79,70,229,0.06)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const [t, rows] = tooltip(payload[0].payload as T);
            return <TooltipBox title={t} rows={rows} />;
          }} />
        <Bar dataKey={y as string} fill={C.primary} radius={[4, 4, 0, 0]} maxBarSize={42}>
          {colorOf && data.map((d, i) => <Cell key={i} fill={colorOf(d)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Part-to-whole bar with legend + values (identity never by colour alone). */
export function SegmentBar({ parts }: { parts: { label: string; value: number; hint?: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  return (
    <div>
      <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full">
        {parts.map((p, i) => p.value > 0 && (
          <div key={p.label} title={`${p.label}: ${p.value}`} className="h-full first:rounded-l-full last:rounded-r-full"
            style={{ width: `${(p.value / total) * 100}%`, background: C.ordinal[i % C.ordinal.length] }} />
        ))}
      </div>
      <ul className="mt-3 grid gap-2 sm:grid-cols-3">
        {parts.map((p, i) => (
          <li key={p.label} className="flex items-start gap-2 text-xs">
            <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: C.ordinal[i % C.ordinal.length] }} />
            <span>
              <span className="font-medium text-ink">{p.label}</span>{" "}
              <span className="tabular text-ink-muted">{num(p.value)} ({num((p.value / total) * 100)}%)</span>
              {p.hint && <span className="block text-ink-muted">{p.hint}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
