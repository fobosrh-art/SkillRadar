"""Pipeline orchestration: explicit task DAG, retries, run history, metrics, alerts.

Task graph (arrow = "depends on"):

    ingest_esco ─────────────────────────────┐
    fetch_live (optional, --live) ─┐         │
    ingest_raw  ◄──────────────────┘         │
    build_silver ◄── ingest_raw              │
    extract_skills ◄── build_silver, ingest_esco
    quality_gate ◄── extract_skills          (BLOCKING checks)
    publish_gold ◄── quality_gate

If a task fails (after its retries) or the quality gate blocks, every downstream task is
`skipped`, so Gold keeps the last valid publication. All tasks are idempotent, so the
recovery procedure is simply to re-run the pipeline.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from ..config import Settings
from ..db import connect, init_db, table_counts, utcnow, utcnow_iso
from ..gold.build import publish_gold
from ..ingestion.esco import load_esco
from ..ingestion.softon_api import fetch_jobs
from ..ingestion.softon_local import ingest_softon_files
from ..quality.checks import QualityGateFailed, run_checks
from ..skills.extractor import extract_all
from ..transform.normalize import parse_ts
from ..transform.silver import build_silver

log = logging.getLogger(__name__)
LOCK_STALE_AFTER = timedelta(hours=2)


@dataclass
class Task:
    name: str
    func: Callable[["RunContext"], dict]
    deps: list[str] = field(default_factory=list)
    retries: int = 0          # extra attempts on unexpected exceptions (not for quality-gate blocks)


@dataclass
class RunContext:
    conn: sqlite3.Connection
    settings: Settings
    run_id: str
    params: dict
    outputs: dict = field(default_factory=dict)


class PipelineLocked(RuntimeError):
    pass


# ----------------------------------------------------------------------------- task functions
def t_ingest_esco(ctx: RunContext) -> dict:
    return load_esco(ctx.conn, ctx.settings.esco_dir, ctx.settings.data_dir, ctx.run_id)


def t_fetch_live(ctx: RunContext) -> dict:
    res = fetch_jobs(ctx.conn, ctx.settings, ctx.run_id, max_pages=ctx.params.get("max_pages"),
                     transport=ctx.params.get("_transport"), sleep=ctx.params.get("_sleep", time.sleep))
    return {"pages": res.pages, "records": res.records, "requests": res.requests, "stop_reason": res.stop_reason,
            "watermark_before": res.watermark_before, "watermark_after": res.watermark_after,
            "snapshot_files": res.snapshot_files}


def t_ingest_raw(ctx: RunContext) -> dict:
    d_from = date.fromisoformat(ctx.params["start"]) if ctx.params.get("start") else None
    d_to = date.fromisoformat(ctx.params["end"]) if ctx.params.get("end") else None
    return ingest_softon_files(ctx.conn, ctx.settings.softon_raw_dir, ctx.settings.data_dir, ctx.run_id, d_from, d_to)


def t_build_silver(ctx: RunContext) -> dict:
    return build_silver(ctx.conn)


def t_extract(ctx: RunContext) -> dict:
    return extract_all(ctx.conn)


def t_quality(ctx: RunContext) -> dict:
    results = run_checks(ctx.conn, ctx.run_id, ctx.settings.min_volume_ratio)
    summary = {r.name: {"passed": r.passed, "severity": r.severity, "failed": r.failed, "checked": r.checked}
               for r in results}
    for r in results:
        if r.severity == "warning" and not r.passed:
            alert(ctx.conn, ctx.settings, ctx.run_id, "warning", f"DQ warning {r.name}: {r.detail}")
    failures = [r for r in results if r.severity == "blocking" and not r.passed]
    if failures:
        raise QualityGateFailed(failures)
    return summary


def t_publish(ctx: RunContext) -> dict:
    return publish_gold(ctx.conn, ctx.run_id, ctx.settings.processed_dir / "gold")


def build_dag(settings: Settings, live: bool) -> list[Task]:
    r = settings.task_retries
    tasks = [Task("ingest_esco", t_ingest_esco, retries=r)]
    raw_deps = []
    if live:
        tasks.append(Task("fetch_live", t_fetch_live))  # the API client has its own HTTP retries/backoff
        raw_deps = ["fetch_live"]
    tasks += [
        Task("ingest_raw", t_ingest_raw, raw_deps, retries=r),
        Task("build_silver", t_build_silver, ["ingest_raw"], retries=r),
        Task("extract_skills", t_extract, ["build_silver", "ingest_esco"], retries=r),
        Task("quality_gate", t_quality, ["extract_skills"]),
        Task("publish_gold", t_publish, ["quality_gate"], retries=r),
    ]
    return tasks


# ----------------------------------------------------------------------------- infrastructure
def alert(conn: sqlite3.Connection, settings: Settings, run_id: str | None, level: str, message: str) -> None:
    """Failure alert: stored in ops_alerts, appended to data/logs/alerts.log and logged to the console."""
    ts = utcnow_iso()
    conn.execute("INSERT INTO ops_alerts(run_id, level, message, created_at) VALUES (?,?,?,?)",
                 (run_id, level, message, ts))
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    with open(settings.log_dir / "alerts.log", "a", encoding="utf-8") as fh:
        fh.write(f"{ts}\t{level.upper()}\t{run_id}\t{message}\n")
    (log.error if level == "error" else log.warning)("ALERT [%s] %s", level, message)


def acquire_lock(conn: sqlite3.Connection, run_id: str) -> None:
    row = conn.execute("SELECT run_id, acquired_at FROM ops_lock WHERE id=1").fetchone()
    if row:
        if utcnow() - parse_ts(row["acquired_at"]) < LOCK_STALE_AFTER:
            raise PipelineLocked(f"pipeline already running (run {row['run_id']} since {row['acquired_at']})")
        log.warning("removing stale lock of run %s", row["run_id"])
        conn.execute("DELETE FROM ops_lock WHERE id=1")
    conn.execute("INSERT INTO ops_lock(id, run_id, acquired_at) VALUES (1,?,?)", (run_id, utcnow_iso()))


def release_lock(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute("DELETE FROM ops_lock WHERE id=1 AND run_id=?", (run_id,))


def _metric(conn, run_id, name, value=None, text=None):
    conn.execute("INSERT INTO ops_metrics(run_id, metric, value, value_text, created_at) VALUES (?,?,?,?,?)",
                 (run_id, name, value, text, utcnow_iso()))


def _rows_out(name: str, out: dict) -> int | None:
    keys = {"ingest_esco": "bronze_esco_skills", "fetch_live": "records", "ingest_raw": "records_loaded",
            "build_silver": "silver_vacancies", "extract_skills": "skill_matches", "publish_gold": "vacancy_count"}
    v = out.get(keys.get(name, ""))
    return v if isinstance(v, int) else None


def run_pipeline(settings: Settings, *, live: bool = False, run_type: str = "pipeline", trigger: str = "cli",
                 params: dict | None = None, sleep: Callable[[float], None] = time.sleep,
                 conn: sqlite3.Connection | None = None) -> dict:
    settings.ensure_dirs()
    own_conn = conn is None
    conn = conn or connect(settings.db_path)
    init_db(conn)
    run_id = f"{utcnow().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    params = dict(params or {})
    public_params = {k: v for k, v in params.items() if not k.startswith("_")}
    t_run = time.perf_counter()
    conn.execute("INSERT INTO ops_pipeline_runs(run_id, run_type, trigger, status, started_at, params_json) "
                 "VALUES (?,?,?,?,?,?)", (run_id, run_type, trigger, "running", utcnow_iso(),
                                          json.dumps({"live": live, **public_params})))
    try:
        acquire_lock(conn, run_id)
    except PipelineLocked as exc:
        conn.execute("UPDATE ops_pipeline_runs SET status='failed', finished_at=?, duration_s=0, error=? WHERE run_id=?",
                     (utcnow_iso(), str(exc), run_id))
        alert(conn, settings, run_id, "error", str(exc))
        if own_conn:
            conn.close()
        return {"run_id": run_id, "status": "failed", "error": str(exc), "tasks": {}}

    ctx = RunContext(conn, settings, run_id, params)
    statuses: dict[str, str] = {}
    run_status, run_error = "success", None
    try:
        for task in build_dag(settings, live):
            blocked_by = [d for d in task.deps if statuses.get(d) != "success"]
            if blocked_by:
                statuses[task.name] = "skipped"
                conn.execute("INSERT INTO ops_task_runs(run_id, task_name, status, attempts, details_json) "
                             "VALUES (?,?,?,0,?)", (run_id, task.name, "skipped",
                                                    json.dumps({"upstream_not_successful": blocked_by})))
                continue
            started, t0, attempt = utcnow_iso(), time.perf_counter(), 0
            out, status, err = {}, "success", None
            while True:
                attempt += 1
                try:
                    out = task.func(ctx) or {}
                    status, err = "success", None
                    break
                except QualityGateFailed as exc:          # deterministic: retrying cannot help
                    status, err = "blocked", str(exc)
                    out = {"failed_checks": [f.name for f in exc.failures]}
                    break
                except Exception as exc:                  # noqa: BLE001 - recorded and alerted
                    status, err = "failed", f"{type(exc).__name__}: {exc}"
                    log.warning("task %s attempt %d failed: %s", task.name, attempt, err)
                    if attempt > task.retries:
                        break
                    sleep(settings.task_retry_delay_s * attempt)
            duration = time.perf_counter() - t0
            statuses[task.name] = status
            ctx.outputs[task.name] = out
            conn.execute(
                """INSERT INTO ops_task_runs(run_id, task_name, status, attempts, started_at, finished_at, duration_s,
                       rows_out, details_json, error) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (run_id, task.name, status, attempt, started, utcnow_iso(), round(duration, 4),
                 _rows_out(task.name, out), json.dumps(out, ensure_ascii=False, default=str), err))
            if status == "blocked":
                run_status, run_error = "blocked", err
                alert(conn, settings, run_id, "error", f"Publication blocked, previous Gold kept. {err}")
            elif status == "failed":
                run_status, run_error = "failed", f"{task.name}: {err}"
                alert(conn, settings, run_id, "error", f"Task {task.name} failed after {attempt} attempt(s): {err}")
    finally:
        duration = time.perf_counter() - t_run
        # run metrics: row counts per layer + freshness of the published dataset
        for name, n in table_counts(conn).items():
            if name.startswith(("bronze_", "silver_", "gold_")):
                _metric(conn, run_id, f"rows.{name}", n)
        pub = conn.execute("SELECT version, published_at, freshness_json FROM gold_publications "
                           "ORDER BY version DESC LIMIT 1").fetchone()
        if pub:
            _metric(conn, run_id, "gold.version", pub["version"])
            for k, v in json.loads(pub["freshness_json"]).items():
                if isinstance(v, (int, float)):
                    _metric(conn, run_id, f"freshness.{k}", v)
        _metric(conn, run_id, "run.duration_s", round(duration, 4))
        conn.execute("UPDATE ops_pipeline_runs SET status=?, finished_at=?, duration_s=?, error=? WHERE run_id=?",
                     (run_status, utcnow_iso(), round(duration, 4), run_error, run_id))
        release_lock(conn, run_id)
    result = {"run_id": run_id, "status": run_status, "error": run_error, "duration_s": round(duration, 3),
              "tasks": statuses, "outputs": ctx.outputs}
    if own_conn:
        conn.close()
    return result


def run_backfill(settings: Settings, start: str, end: str, trigger: str = "cli", **kw) -> dict:
    """Re-process raw snapshots whose snapshot date is in [start, end] (inclusive), then rebuild
    Silver/Gold. Idempotent: snapshots already in Bronze are not loaded twice."""
    date.fromisoformat(start), date.fromisoformat(end)  # validate
    if start > end:
        raise ValueError("start must be <= end")
    return run_pipeline(settings, run_type="backfill", trigger=trigger, params={"start": start, "end": end}, **kw)
