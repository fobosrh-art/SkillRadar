import { useCallback, useEffect, useRef, useState } from "react";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
  });
  const text = await res.text();
  let body: any = null; // eslint-disable-line @typescript-eslint/no-explicit-any
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { detail: `${res.status} ${res.statusText || "error"}: ${text.slice(0, 120)}` };
  }
  if (!res.ok) {
    const detail = body?.detail;
    const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : res.statusText;
    throw new ApiError(res.status, msg || `HTTP ${res.status}`);
  }
  return body as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  /** Administrative calls carry the anti-CSRF header the backend requires (localhost only). */
  admin: <T,>(path: string, body?: unknown, method = "POST") =>
    request<T>(path, {
      method,
      headers: { "X-SkillRadar-Admin": "1" },
      body: method === "GET" ? undefined : JSON.stringify(body ?? {}),
    }),
};

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** GET a JSON endpoint; `path = null` disables the request. Keeps previous data while reloading. */
export function useApi<T>(path: string | null, opts?: { pollMs?: number }): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    if (!path) return;
    const id = ++seq.current;
    setLoading(true);
    api
      .get<T>(path)
      .then((d) => {
        if (id === seq.current) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => id === seq.current && setError(e.message))
      .finally(() => id === seq.current && setLoading(false));
  }, [path, tick]);

  useEffect(() => {
    if (!opts?.pollMs || !path) return;
    const t = setInterval(() => setTick((x) => x + 1), opts.pollMs);
    return () => clearInterval(t);
  }, [opts?.pollMs, path]);

  const reload = useCallback(() => setTick((x) => x + 1), []);
  return { data, error, loading, reload };
}

/** Persisted per-browser state (career selection, roadmap checklist). Tolerates blocked storage. */
export function useStored<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });
  const set = useCallback(
    (v: T | ((p: T) => T)) => {
      setValue((prev) => {
        const next = typeof v === "function" ? (v as (p: T) => T)(prev) : v;
        try {
          localStorage.setItem(key, JSON.stringify(next));
        } catch {
          /* storage unavailable: keep in memory */
        }
        return next;
      });
    },
    [key],
  );
  return [value, set];
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
