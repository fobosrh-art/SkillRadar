"""Administrative operations for the website (localhost only).

Protection layers:
  1. The server binds to 127.0.0.1 (start.cmd / `python -m skillradar web`).
  2. `require_admin` rejects any client whose address is not loopback.
  3. A custom header `X-SkillRadar-Admin: 1` is required. Browsers cannot send custom headers
     cross-origin without a CORS preflight, and this app enables no CORS - so a malicious web
     page cannot trigger operations (CSRF protection). The Origin, if present, must be local.
  4. Optional `SKILLRADAR_ADMIN_TOKEN` (env): if set, the `X-Admin-Token` header must match.
Concurrency: one process-wide lock (shared with the web scheduler) + the database `ops_lock`
(which also blocks overlap with a CLI run). A second request gets HTTP 409.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import traceback
import uuid
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from ..config import Settings
from ..db import connect, init_db, utcnow, utcnow_iso
from ..demo import run_demo
from ..pipeline.runner import run_backfill, run_pipeline

log = logging.getLogger(__name__)
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
LOCAL_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
RUN_LOCK = threading.Lock()


def trusted_hosts(request: Request) -> set[str]:
    """Loopback only, plus hosts explicitly listed in SKILLRADAR_ADMIN_TRUSTED_HOSTS (comma-separated).
    The extra list exists only for the optional Docker setup, where requests arrive from the bridge gateway."""
    base = set(getattr(request.app.state, "trusted_hosts", LOOPBACK))
    extra = {h.strip() for h in os.getenv("SKILLRADAR_ADMIN_TRUSTED_HOSTS", "").split(",") if h.strip()}
    return base | extra


def require_admin(request: Request) -> None:
    trusted = trusted_hosts(request)
    host = request.client.host if request.client else None
    if host not in trusted:
        raise HTTPException(403, "Administrative endpoints are restricted to localhost")
    if request.headers.get("x-skillradar-admin") != "1":
        raise HTTPException(403, "Missing X-SkillRadar-Admin header")
    origin = request.headers.get("origin")
    if origin and urlparse(origin).hostname not in LOCAL_ORIGIN_HOSTS:
        raise HTTPException(403, "Cross-origin administrative request refused")
    token = os.getenv("SKILLRADAR_ADMIN_TOKEN")
    if token and request.headers.get("x-admin-token") != token:
        raise HTTPException(401, "Invalid admin token")


def is_local(request: Request) -> bool:
    trusted = trusted_hosts(request)
    return bool(request.client and request.client.host in trusted)


class OperationManager:
    def __init__(self, settings_factory):
        self.settings_factory = settings_factory
        self.current: str | None = None

    # --------------------------------------------------------------- persistence
    def _conn(self):
        conn = connect(self.settings_factory().db_path)
        init_db(conn)
        return conn

    def _update(self, op_id: str, **fields) -> None:
        conn = self._conn()
        try:
            sets = ", ".join(f"{k}=?" for k in fields)
            conn.execute(f"UPDATE ops_admin_operations SET {sets} WHERE op_id=?", (*fields.values(), op_id))
        finally:
            conn.close()

    def get(self, op_id: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM ops_admin_operations WHERE op_id=?", (op_id,)).fetchone()
            return _decode(row) if row else None
        finally:
            conn.close()

    def recent(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        try:
            return [_decode(r) for r in conn.execute(
                "SELECT * FROM ops_admin_operations ORDER BY requested_at DESC LIMIT ?", (limit,))]
        finally:
            conn.close()

    def db_lock_holder(self) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute("SELECT run_id, acquired_at FROM ops_lock WHERE id=1").fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # --------------------------------------------------------------- execution
    def submit(self, kind: str, params: dict) -> dict:
        if not RUN_LOCK.acquire(blocking=False):
            raise HTTPException(409, f"Another operation is running ({self.current or 'scheduled pipeline run'})")
        holder = self.db_lock_holder()
        if holder:
            RUN_LOCK.release()
            raise HTTPException(409, f"Pipeline run {holder['run_id']} is in progress (database lock)")
        op_id = f"op-{utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
        conn = self._conn()
        try:
            conn.execute("INSERT INTO ops_admin_operations(op_id, kind, status, params_json, requested_at) "
                         "VALUES (?,?,?,?,?)", (op_id, kind, "queued", json.dumps(params), utcnow_iso()))
        finally:
            conn.close()
        self.current = op_id
        threading.Thread(target=self._execute, args=(op_id, kind, params), daemon=True, name=op_id).start()
        return self.get(op_id)

    def _execute(self, op_id: str, kind: str, params: dict) -> None:
        settings: Settings = self.settings_factory()
        self._update(op_id, status="running", started_at=utcnow_iso())
        try:
            if kind == "run":
                res = run_pipeline(settings, trigger="web")
            elif kind == "fetch_live":
                res = run_pipeline(settings, live=True, trigger="web", params={"max_pages": params["max_pages"]})
            elif kind == "backfill":
                res = run_backfill(settings, params["start"], params["end"], trigger="web")
            elif kind.startswith("demo:"):
                res = run_demo(settings, kind.split(":", 1)[1])
                res = {"status": "success" if res["passed"] else "failed", "run_id": None, "demo": res,
                       "error": None if res["passed"] else "one or more demo expectations were not met"}
            else:
                raise ValueError(f"unknown operation {kind}")
            summary = {k: v for k, v in res.items() if k != "outputs"}
            if "outputs" in res:      # keep a compact, secret-free view of task outputs
                summary["outputs"] = {k: _compact(v) for k, v in res["outputs"].items()}
            self._update(op_id, status=res["status"], finished_at=utcnow_iso(), run_id=res.get("run_id"),
                         result_json=json.dumps(summary, ensure_ascii=False, default=str), error=res.get("error"))
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            log.error("operation %s failed: %s", op_id, traceback.format_exc())
            self._update(op_id, status="failed", finished_at=utcnow_iso(), error=f"{type(exc).__name__}: {exc}")
        finally:
            self.current = None
            RUN_LOCK.release()


def _compact(v):
    if isinstance(v, dict):
        return {k: (x if not isinstance(x, (list, dict)) or len(json.dumps(x, default=str)) < 600 else "…")
                for k, x in v.items() if k not in ("snapshot_files",)}
    return v


def _decode(row) -> dict:
    d = dict(row)
    for k in ("params_json", "result_json"):
        if d.get(k):
            d[k.replace("_json", "")] = json.loads(d.pop(k))
        else:
            d.pop(k, None)
            d[k.replace("_json", "")] = None
    return d
