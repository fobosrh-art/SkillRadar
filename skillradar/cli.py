"""SkillRadar command line.  Usage:  python -m skillradar <command> [options]

  init-db                 create/upgrade the SQLite schema
  ingest-esco             load ESCO CSVs into Bronze (skips if unchanged)
  ingest-local            register local raw Softon JSON files into Bronze (no network)
  fetch-live              call the Softon API (explicit; uses request budget)
  run [--live]            run the full pipeline (local data unless --live)
  backfill --start --end  re-process raw snapshots in a date range, then rebuild Silver/Gold
  schedule [--live]       start the APScheduler loop
  status                  last runs, DQ results, row counts, freshness, API budget
  web [--port 8000]       start the website + API on http://127.0.0.1:8000 (localhost only)
  demo <name>             safe sandbox demonstration (idempotency | failed_validation | backfill | source_failure)
  repair-watermark        recompute incremental state from stored API snapshots (no network)
  reanonymize-bronze      re-apply current PII rules to stored Bronze payloads
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import get_settings
from .db import connect, init_db, table_counts


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_init_db(s, a):
    s.ensure_dirs()
    conn = connect(s.db_path)
    init_db(conn)
    print(f"database ready: {s.db_path}")


def cmd_ingest_esco(s, a):
    from .ingestion.esco import load_esco
    conn = connect(s.db_path)
    init_db(conn)
    _print(load_esco(conn, s.esco_dir, s.data_dir, force=a.force))


def cmd_ingest_local(s, a):
    from .ingestion.softon_local import ingest_softon_files
    conn = connect(s.db_path)
    init_db(conn)
    _print(ingest_softon_files(conn, s.softon_raw_dir, s.data_dir, run_id=None))


def cmd_fetch_live(s, a):
    from .ingestion.softon_api import SourceError, fetch_jobs, remaining_budget
    conn = connect(s.db_path)
    init_db(conn)
    print(f"remaining request budget this month: {remaining_budget(conn, s)}")
    try:
        res = fetch_jobs(conn, s, run_id=None, max_pages=a.max_pages, full=a.full)
    except SourceError as exc:
        print(f"live fetch failed: {exc}", file=sys.stderr)
        sys.exit(2)
    _print(res.__dict__)
    print("Raw snapshots saved and loaded into Bronze. Run `python -m skillradar run` to rebuild Silver/Gold.")


def _report(result):
    _print({k: v for k, v in result.items() if k != "outputs"})
    if result["status"] != "success":
        sys.exit(1)


def cmd_run(s, a):
    from .pipeline.runner import run_pipeline
    _report(run_pipeline(s, live=a.live, params={"max_pages": a.max_pages} if a.max_pages else None))


def cmd_backfill(s, a):
    from .pipeline.runner import run_backfill
    _report(run_backfill(s, a.start, a.end))


def cmd_schedule(s, a):
    from .pipeline.scheduler import start_scheduler
    start_scheduler(s, live=a.live, interval_hours=a.hours, retry_minutes=a.retry_minutes)


def cmd_status(s, a):
    from .ingestion.softon_api import remaining_budget, requests_used_this_month
    conn = connect(s.db_path)
    init_db(conn)
    runs = [dict(r) for r in conn.execute(
        "SELECT run_id, run_type, trigger, status, started_at, duration_s, error FROM ops_pipeline_runs "
        "ORDER BY started_at DESC LIMIT ?", (a.limit,))]
    last = runs[0]["run_id"] if runs else None
    tasks = [dict(r) for r in conn.execute(
        "SELECT task_name, status, attempts, duration_s, rows_out FROM ops_task_runs WHERE run_id=? ORDER BY id",
        (last,))]
    dq = [dict(r) for r in conn.execute(
        "SELECT check_name, severity, passed, checked_count, failed_count FROM ops_dq_results WHERE run_id=? "
        "ORDER BY id", (last,))]
    pub = conn.execute("SELECT * FROM gold_publications ORDER BY version DESC LIMIT 1").fetchone()
    _print({"recent_runs": runs, "last_run_tasks": tasks, "last_run_dq": dq,
            "current_gold": dict(pub) if pub else None, "row_counts": table_counts(conn),
            "api_budget": {"used_this_month": requests_used_this_month(conn),
                           "remaining": remaining_budget(conn, s), "monthly_budget": s.softon_monthly_budget},
            "recent_alerts": [dict(r) for r in conn.execute(
                "SELECT created_at, level, message FROM ops_alerts ORDER BY id DESC LIMIT 5")]})


def cmd_generate_demo(s, a):
    from .demo_data import generate
    if not s.demo_mode:
        print("Refusing: set SKILLRADAR_DEMO=1 (and a separate SKILLRADAR_DATA_DIR) to generate synthetic demo data.",
              file=sys.stderr)
        sys.exit(2)
    _print(generate(s.data_dir, force=a.force))


def cmd_web(s, a):
    import uvicorn
    s.ensure_dirs()
    conn = connect(s.db_path)
    init_db(conn)
    conn.close()
    print(f"SkillRadar: http://{a.host}:{a.port}")
    uvicorn.run("skillradar.web.app:app", host=a.host, port=a.port, reload=False, log_level="info")


def cmd_demo(s, a):
    from .demo import run_demo
    res = run_demo(s, a.name)
    for st in res["steps"]:
        mark = "PASS" if st["ok"] else "FAIL"
        print(f"[{mark}] step {st['step']}: {st['title']}")
        print(f"       expected: {st['expected']}")
        print(f"       run: {st['run_status']}  gold: {st['state']}")
    print(f"demo {a.name}: {'PASSED' if res['passed'] else 'FAILED'} (sandbox {res['sandbox']})")
    if not res["passed"]:
        sys.exit(1)


def cmd_reanonymize(s, a):
    from .ingestion.softon_local import reanonymize_bronze
    conn = connect(s.db_path)
    init_db(conn)
    _print(reanonymize_bronze(conn))


def cmd_repair_watermark(s, a):
    from .ingestion.softon_api import get_state, replay_state_from_snapshots
    conn = connect(s.db_path)
    init_db(conn)
    before = get_state(conn)
    after = replay_state_from_snapshots(conn, s.data_dir)
    _print({"before": {k: before.get(k) for k in ("watermark", "resume_cursor")} | {
        "resume_cursor": bool(before.get("resume_cursor"))}, "after": after})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skillradar", description="SkillRadar data pipeline")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db").set_defaults(func=cmd_init_db)
    e = sub.add_parser("ingest-esco")
    e.add_argument("--force", action="store_true", help="reload even if file hashes are unchanged")
    e.set_defaults(func=cmd_ingest_esco)
    sub.add_parser("ingest-local").set_defaults(func=cmd_ingest_local)
    f = sub.add_parser("fetch-live", help="LIVE Softon API call (uses request budget)")
    f.add_argument("--max-pages", type=int, default=None)
    f.add_argument("--full", action="store_true", help="ignore the watermark (newest-first walk)")
    f.set_defaults(func=cmd_fetch_live)
    r = sub.add_parser("run")
    r.add_argument("--live", action="store_true", help="also fetch from the Softon API first")
    r.add_argument("--max-pages", type=int, default=None)
    r.set_defaults(func=cmd_run)
    b = sub.add_parser("backfill")
    b.add_argument("--start", required=True, help="YYYY-MM-DD (snapshot date, inclusive)")
    b.add_argument("--end", required=True, help="YYYY-MM-DD (inclusive)")
    b.set_defaults(func=cmd_backfill)
    sc = sub.add_parser("schedule")
    sc.add_argument("--live", action="store_true")
    sc.add_argument("--hours", type=float, default=None)
    sc.add_argument("--retry-minutes", type=int, default=15)
    sc.set_defaults(func=cmd_schedule)
    st = sub.add_parser("status")
    st.add_argument("--limit", type=int, default=5)
    st.set_defaults(func=cmd_status)
    for name in ("web", "api"):        # "api" kept as an alias of the Phase-1 command
        ap = sub.add_parser(name)
        ap.add_argument("--host", default="127.0.0.1")
        ap.add_argument("--port", type=int, default=8000)
        ap.set_defaults(func=cmd_web)
    gd = sub.add_parser("generate-demo-data", help="write the SYNTHETIC demo dataset (demo mode only)")
    gd.add_argument("--force", action="store_true")
    gd.set_defaults(func=cmd_generate_demo)
    dm = sub.add_parser("demo")
    dm.add_argument("name", choices=["idempotency", "failed_validation", "backfill", "source_failure"])
    dm.set_defaults(func=cmd_demo)
    sub.add_parser("repair-watermark").set_defaults(func=cmd_repair_watermark)
    sub.add_parser("reanonymize-bronze").set_defaults(func=cmd_reanonymize)
    return p


def main(argv=None) -> None:
    for stream in (sys.stdout, sys.stderr):      # Windows consoles default to cp1251/cp437
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    args.func(get_settings(), args)


if __name__ == "__main__":
    main()
