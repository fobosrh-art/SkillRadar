"""Live Softon Job Data API client.

Contract verified against the official schema (https://api.softon.dev/v1/schema, saved
in docs/vendor/softon_schema.json):
  * GET /v1/jobs, `Authorization: Bearer <key>`
  * `limit` 1-100, `cursor` = previous response's `meta.next` (null on last page)
  * `updated_after` = only rows whose `ingested_at` is STRICTLY later (incremental tailing)
  * `order` = ingested_at | posted_at (prefix `-` to reverse)
  * 429 `rate_limited` is retryable (Retry-After); 429 `quota_exceeded` is not
  * Budget headers: X-Quota-Limit / X-Quota-Used; a credit = one 2xx response

No-skip incremental strategy (see docs/architecture.md, "Incremental live loading"):
  * Walk `updated_after=<watermark>&order=ingested_at` (ascending, keyset cursor).
  * Softon ingests in batches, so many rows share one `ingested_at` (observed: 99 of 100
    rows on a page). Because `updated_after` is strict, setting the watermark to the
    last timestamp of an unfinished page would SKIP the remaining rows of that batch.
    Therefore, while a walk is unfinished:
      - the next cursor (+ the exact params it belongs to) is stored as a resume point, and
      - the watermark only advances to the newest timestamp that is strictly older than
        the page's last timestamp (that batch is provably complete).
  * When the walk reaches the last page, the watermark becomes the newest timestamp seen
    and the resume point is cleared.
  * If a stored cursor is rejected (HTTP 400), it is discarded and the walk restarts from
    the (tie-safe) watermark - re-fetched rows are de-duplicated downstream.

This module only runs when explicitly invoked (`fetch-live` or `run --live`).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from ..config import Settings
from ..db import utcnow, utcnow_iso
from .softon_local import ingest_softon_files

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {500, 502, 503, 504}


class SourceError(RuntimeError):
    """The source could not deliver data (after retries) or must not be called."""


class BudgetExceeded(SourceError):
    pass


class InvalidCursor(SourceError):
    pass


@dataclass
class FetchResult:
    pages: int = 0
    records: int = 0
    requests: int = 0
    snapshot_files: list[str] | None = None
    watermark_before: str | None = None
    watermark_after: str | None = None
    resumed_from_cursor: bool = False
    resume_pending: bool = False
    exhausted: bool = False
    stop_reason: str = ""


def requests_used_this_month(conn: sqlite3.Connection) -> int:
    month = utcnow().strftime("%Y-%m")
    return conn.execute(
        "SELECT COUNT(*) FROM ops_api_requests WHERE substr(requested_at,1,7)=? AND status_code BETWEEN 200 AND 299",
        (month,)).fetchone()[0]


def remaining_budget(conn: sqlite3.Connection, settings: Settings) -> int:
    local = settings.softon_monthly_budget - requests_used_this_month(conn)
    month = utcnow().strftime("%Y-%m")
    last = conn.execute(
        """SELECT quota_limit, quota_used FROM ops_api_requests
           WHERE quota_limit IS NOT NULL AND substr(requested_at,1,7)=? ORDER BY id DESC LIMIT 1""",
        (month,)).fetchone()
    if last is not None:
        local = min(local, last["quota_limit"] - last["quota_used"])
    return max(local, 0)


# ----------------------------------------------------------------------------- incremental state
def get_state(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM ops_watermarks WHERE source='softon'").fetchone()
    return dict(row) if row else {}


def current_watermark(conn: sqlite3.Connection) -> str | None:
    """Stored watermark; before the first live walk, fall back to the newest Bronze `ingested_at`
    (the provided export). That fallback only bounds *coverage* (older unseen postings are not
    back-filled) - documented limitation."""
    state = get_state(conn)
    if state.get("watermark"):
        return state["watermark"]
    return conn.execute("SELECT MAX(source_ingested_at) FROM bronze_softon_jobs").fetchone()[0]


def _save_state(conn: sqlite3.Connection, run_id: str | None, watermark: str | None,
                cursor: str | None, params: dict | None) -> None:
    prev = get_state(conn).get("watermark")
    wm = max([v for v in (prev, watermark) if v], default=None)
    if wm is None:
        return
    conn.execute(
        """INSERT INTO ops_watermarks(source, watermark, updated_at, run_id, resume_cursor, resume_params)
           VALUES ('softon',?,?,?,?,?)
           ON CONFLICT(source) DO UPDATE SET watermark=excluded.watermark, updated_at=excluded.updated_at,
               run_id=excluded.run_id, resume_cursor=excluded.resume_cursor, resume_params=excluded.resume_params""",
        (wm, utcnow_iso(), run_id, cursor, json.dumps(params, ensure_ascii=False) if params else None))


def tie_safe_watermark(stamps: list[str], has_next: bool) -> str | None:
    """Highest timestamp whose batch is complete on this (ascending) page."""
    if not stamps:
        return None
    if not has_next:
        return max(stamps)
    last = max(stamps)
    older = [s for s in stamps if s < last]
    return max(older) if older else None


def replay_state_from_snapshots(conn: sqlite3.Connection, data_dir: Path) -> dict:
    """Recompute watermark + resume cursor from the stored API snapshots with the no-skip rules
    (used once to repair state written by the earlier, tie-unsafe version)."""
    files = conn.execute("""SELECT path FROM bronze_raw_files
                            WHERE source='softon' AND file_kind='api_snapshot' ORDER BY snapshot_at""").fetchall()
    base = conn.execute("""SELECT MAX(b.source_ingested_at) FROM bronze_softon_jobs b
                           JOIN bronze_raw_files f USING(file_id) WHERE f.file_kind='local_export'""").fetchone()[0]
    wm, cursor, params = base, None, None
    for f in files:
        doc = json.loads((Path(data_dir) / f["path"]).read_text(encoding="utf-8-sig"))
        meta_path = (Path(data_dir) / f["path"]).with_name(Path(f["path"]).stem + ".meta.json")
        page_params = json.loads(meta_path.read_text(encoding="utf-8")).get("params") if meta_path.exists() else None
        if not page_params or page_params.get("order") != "ingested_at":
            continue
        stamps = [r.get("ingested_at") for r in doc.get("data", []) if r.get("ingested_at")]
        nxt = (doc.get("meta") or {}).get("next")
        safe = tie_safe_watermark(stamps, bool(nxt))
        wm = max([v for v in (wm, safe) if v], default=None)
        cursor, params = (nxt, page_params) if nxt else (None, None)
    conn.execute("DELETE FROM ops_watermarks WHERE source='softon'")
    if wm:
        conn.execute("""INSERT INTO ops_watermarks(source, watermark, updated_at, run_id, resume_cursor, resume_params)
                        VALUES ('softon',?,?,?,?,?)""",
                     (wm, utcnow_iso(), "repair", cursor, json.dumps(params, ensure_ascii=False) if params else None))
    return {"watermark": wm, "resume_cursor_stored": bool(cursor), "resume_params": params}


# ----------------------------------------------------------------------------- HTTP
def _int_header(resp: httpx.Response, name: str) -> int | None:
    try:
        return int(resp.headers.get(name)) if resp.headers.get(name) is not None else None
    except ValueError:
        return None


def _log_request(conn, run_id, params, status, duration_ms, records, resp, attempt, error=None):
    safe = {k: v for k, v in params.items() if k != "cursor"}
    if "cursor" in params:
        safe["cursor"] = "<opaque>"
    conn.execute(
        """INSERT INTO ops_api_requests(run_id, requested_at, endpoint, params_json, status_code, duration_ms,
                records, quota_limit, quota_used, attempt, error) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, utcnow_iso(), "/v1/jobs", json.dumps(safe, ensure_ascii=False), status, duration_ms, records,
         _int_header(resp, "X-Quota-Limit") if resp is not None else None,
         _int_header(resp, "X-Quota-Used") if resp is not None else None, attempt, error))


def _get_with_retries(client: httpx.Client, conn, settings: Settings, run_id, params: dict,
                      sleep: Callable[[float], None]) -> httpx.Response:
    last_error = "unknown"
    for attempt in range(1, settings.softon_max_retries + 2):
        t0 = time.perf_counter()
        resp = None
        try:
            resp = client.get("/jobs", params=params)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            _log_request(conn, run_id, params, None, (time.perf_counter() - t0) * 1000, None, None, attempt, last_error)
        else:
            ms = (time.perf_counter() - t0) * 1000
            if 200 <= resp.status_code < 300:
                return resp  # logged by caller once the record count is known
            code = ""
            try:
                code = (resp.json().get("error") or {}).get("code", "")
            except ValueError:
                pass
            last_error = f"HTTP {resp.status_code} {code}".strip()
            _log_request(conn, run_id, params, resp.status_code, ms, None, resp, attempt, last_error)
            if resp.status_code == 429 and code == "quota_exceeded":
                raise BudgetExceeded("Softon monthly quota exceeded (quota_exceeded)")
            if resp.status_code == 400 and "cursor" in params:
                raise InvalidCursor(f"stored cursor rejected: {last_error}")
            if not (resp.status_code in RETRYABLE_STATUS or resp.status_code == 429):
                raise SourceError(f"Softon request failed, not retryable: {last_error}")
        if attempt <= settings.softon_max_retries:
            delay = settings.softon_backoff_s * (2 ** (attempt - 1))
            if resp is not None and resp.status_code == 429 and resp.headers.get("Retry-After"):
                try:
                    delay = max(delay, float(resp.headers["Retry-After"]))
                except ValueError:
                    pass
            log.warning("Softon attempt %d failed (%s); retrying in %.1fs", attempt, last_error, delay)
            sleep(delay)
    raise SourceError(f"Softon unavailable after {settings.softon_max_retries + 1} attempts: {last_error}")


def _write_snapshot(settings: Settings, body: bytes, fetched_at: str, page: int, request: dict) -> Path:
    ts = fetched_at.replace("-", "").replace(":", "").replace(".", "")
    day_dir = settings.snapshot_dir / fetched_at[:4] / fetched_at[5:7] / fetched_at[8:10]
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"softon_jobs_{ts}_p{page:03d}.json"
    with open(path, "xb") as fh:  # 'x' = never overwrite an existing raw snapshot
        fh.write(body)
    meta = {"fetched_at": fetched_at, "page": page, "endpoint": "/v1/jobs", "params": request}
    with open(path.with_name(path.stem + ".meta.json"), "x", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    return path


def fetch_jobs(conn: sqlite3.Connection, settings: Settings, run_id: str | None, max_pages: int | None = None,
               transport: httpx.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep,
               full: bool = False) -> FetchResult:
    key = settings.softon_api_key
    if not key:
        raise SourceError("SOFTON_API_KEY is not set (put it in .env); live fetch refused")
    max_pages = max_pages or settings.softon_max_pages_per_run
    settings.ensure_dirs()

    res = FetchResult(snapshot_files=[])
    state = get_state(conn)
    res.watermark_before = None if full else current_watermark(conn)
    base = {"city": settings.softon_city, "limit": min(settings.softon_page_limit, 100), "include": "bodies"}
    incremental = bool(res.watermark_before)
    cursor = None
    if incremental and state.get("resume_cursor") and state.get("resume_params"):
        params = json.loads(state["resume_params"])           # continue the unfinished walk exactly
        cursor = state["resume_cursor"]
        res.resumed_from_cursor = True
    elif incremental:
        params = dict(base, updated_after=res.watermark_before, order="ingested_at")
    else:
        params = dict(base)                                   # newest-first (default order)
    newest_seen: str | None = None

    with httpx.Client(base_url=settings.softon_base_url, timeout=settings.softon_timeout_s, transport=transport,
                      headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                               "User-Agent": "SkillRadar-university-project/1.0"}) as client:
        while res.pages < max_pages:
            left = remaining_budget(conn, settings)   # min(local budget, X-Quota-Limit - X-Quota-Used)
            if left <= settings.softon_quota_reserve:
                res.stop_reason = f"request budget low ({left} left, reserve {settings.softon_quota_reserve})"
                if res.pages == 0:
                    raise BudgetExceeded(f"Request budget too low: {left} left, reserve {settings.softon_quota_reserve}")
                break
            if res.pages > 0 and settings.softon_page_delay_s > 0:
                sleep(settings.softon_page_delay_s)       # respect the per-second rate limit
            page_params = dict(params, **({"cursor": cursor} if cursor else {}))
            t0 = time.perf_counter()
            try:
                resp = _get_with_retries(client, conn, settings, run_id, page_params, sleep)
            except InvalidCursor:
                log.warning("resume cursor rejected; restarting from watermark %s", res.watermark_before)
                conn.execute("UPDATE ops_watermarks SET resume_cursor=NULL, resume_params=NULL WHERE source='softon'")
                params = dict(base, updated_after=current_watermark(conn), order="ingested_at")
                cursor, res.resumed_from_cursor = None, False
                continue
            res.requests += 1
            body = resp.content
            doc = json.loads(body.decode("utf-8-sig"))
            rows = doc.get("data") or []
            _log_request(conn, run_id, page_params, resp.status_code, (time.perf_counter() - t0) * 1000,
                         len(rows), resp, 1)
            fetched_at = utcnow_iso()
            path = _write_snapshot(settings, body, fetched_at, res.pages + 1,
                                   {k: v for k, v in page_params.items() if k != "cursor"})
            res.snapshot_files.append(str(path))
            ingest_softon_files(conn, settings.softon_raw_dir, settings.data_dir, run_id, files=[path])
            res.pages += 1
            res.records += len(rows)
            stamps = [r.get("ingested_at") for r in rows if isinstance(r, dict) and r.get("ingested_at")]
            if stamps:
                newest_seen = max([newest_seen, *stamps]) if newest_seen else max(stamps)
            cursor = (doc.get("meta") or {}).get("next")
            if incremental:
                # page is persisted in Bronze before the state moves -> crash-safe
                safe = tie_safe_watermark(stamps, bool(cursor))
                floor = max([v for v in (safe, res.watermark_before) if v], default=None)
                _save_state(conn, run_id, floor, cursor, params if cursor else None)
            if not cursor:
                res.exhausted = True
                res.stop_reason = "last page reached"
                break
        else:
            res.stop_reason = f"max_pages={max_pages} reached"
    # A full (newest-first) walk only sets the watermark if it reached the last page.
    if not incremental and res.exhausted and newest_seen:
        _save_state(conn, run_id, newest_seen, None, None)
    res.resume_pending = bool(get_state(conn).get("resume_cursor"))
    res.watermark_after = current_watermark(conn)
    return res
