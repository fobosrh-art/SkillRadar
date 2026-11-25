"""Scheduled execution (APScheduler).

Two modes, same job function:
  * CLI  - `python -m skillradar schedule`: BlockingScheduler in the foreground (Ctrl+C to stop).
  * Web  - the website process can host a BackgroundScheduler, toggled from the Admin page
           (localhost only). Web-scheduled runs never call the live API.

Behaviour: interval job (default 6 h), `max_instances=1` + `coalesce=True`, and ONE recovery
retry `retry_minutes` after a failed/blocked run. State (enabled, next run, last status,
heartbeat) is written to `ops_scheduler_state`, so the Pipeline Monitor can show it.
Live API calls happen only in CLI mode with an explicit `--live`.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from ..config import Settings
from ..db import connect, init_db, utcnow_iso
from .runner import run_pipeline

log = logging.getLogger(__name__)
JOB_ID = "skillradar_pipeline"


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def write_state(settings: Settings, **fields) -> None:
    conn = connect(settings.db_path)
    try:
        init_db(conn)
        row = conn.execute("SELECT * FROM ops_scheduler_state WHERE id=1").fetchone()
        state = dict(row) if row else {"id": 1, "enabled": 0, "mode": "cli", "interval_hours": 6.0, "live": 0}
        state.update(fields, heartbeat_at=utcnow_iso())
        cols = ["id", "enabled", "mode", "interval_hours", "live", "started_at", "last_run_at", "last_run_id",
                "last_status", "next_run_at", "heartbeat_at"]
        conn.execute(f"INSERT OR REPLACE INTO ops_scheduler_state({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                     [state.get(c) for c in cols])
    finally:
        conn.close()


def _next_run(scheduler) -> str | None:
    if scheduler is None:
        return None
    job = scheduler.get_job(JOB_ID)
    return _iso(job.next_run_time) if job and job.next_run_time else None


def scheduled_job(settings: Settings, live: bool, scheduler=None, retry_minutes: int = 15, is_retry: bool = False,
                  record_state: bool = True):
    result = run_pipeline(settings, live=live, trigger="scheduler_retry" if is_retry else "scheduler")
    log.info("scheduled run %s finished: %s (%.2fs)", result["run_id"], result["status"], result.get("duration_s") or 0)
    if result["status"] != "success" and scheduler is not None and not is_retry:
        when = datetime.now(timezone.utc) + timedelta(minutes=retry_minutes)
        scheduler.add_job(scheduled_job, "date", run_date=when, id="recovery_retry", replace_existing=True,
                          kwargs=dict(settings=settings, live=live, scheduler=None, retry_minutes=retry_minutes,
                                      is_retry=True, record_state=record_state))
        log.warning("run %s; recovery retry scheduled at %s", result["status"], when.isoformat())
    if record_state:
        try:
            write_state(settings, last_run_at=utcnow_iso(), last_run_id=result["run_id"],
                        last_status=result["status"],
                        next_run_at=_next_run(scheduler) if hasattr(scheduler, "get_job") else None)
        except Exception:  # noqa: BLE001 - state is informational only
            log.exception("could not record scheduler state")
    return result


def start_scheduler(settings: Settings, live: bool = False, interval_hours: float | None = None,
                    retry_minutes: int = 15) -> None:
    hours = interval_hours or settings.schedule_interval_hours
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(scheduled_job, "interval", hours=hours, id=JOB_ID, max_instances=1,
                  coalesce=True, next_run_time=datetime.now(timezone.utc),
                  kwargs=dict(settings=settings, live=live, scheduler=sched, retry_minutes=retry_minutes))
    write_state(settings, enabled=1, mode="cli", interval_hours=hours, live=int(live), started_at=utcnow_iso())
    log.info("scheduler started: every %.2fh, live=%s. Ctrl+C to stop.", hours, live)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")
    finally:
        write_state(settings, enabled=0, next_run_at=None)


class WebScheduler:
    """BackgroundScheduler owned by the web process. Local pipeline only (never live)."""

    def __init__(self, settings: Settings, run_lock: threading.Lock):
        self.settings = settings
        self.run_lock = run_lock          # shared with admin operations -> no concurrent runs
        self.sched: BackgroundScheduler | None = None
        self.interval_hours = settings.schedule_interval_hours

    @property
    def enabled(self) -> bool:
        return self.sched is not None and self.sched.running

    def _job(self):
        if not self.run_lock.acquire(blocking=False):
            log.warning("scheduled run skipped: another operation is running")
            write_state(self.settings, last_status="skipped_busy", next_run_at=_next_run(self.sched))
            return None
        try:
            return scheduled_job(self.settings, live=False, scheduler=self.sched)
        finally:
            self.run_lock.release()

    def start(self, interval_hours: float, run_now: bool = False) -> None:
        self.stop()
        self.interval_hours = interval_hours
        self.sched = BackgroundScheduler(timezone="UTC")
        first = datetime.now(timezone.utc) + (timedelta(seconds=1) if run_now else timedelta(hours=interval_hours))
        self.sched.add_job(self._job, "interval", hours=interval_hours, id=JOB_ID, max_instances=1, coalesce=True,
                           next_run_time=first)
        self.sched.start()
        write_state(self.settings, enabled=1, mode="web", interval_hours=interval_hours, live=0,
                    started_at=utcnow_iso(), next_run_at=_iso(first))

    def stop(self) -> None:
        if self.sched is not None:
            try:
                self.sched.shutdown(wait=False)
            except Exception:  # noqa: BLE001
                pass
            self.sched = None
            write_state(self.settings, enabled=0, next_run_at=None)

    def status(self) -> dict:
        return {"enabled": self.enabled, "interval_hours": self.interval_hours, "next_run_at": _next_run(self.sched)}
