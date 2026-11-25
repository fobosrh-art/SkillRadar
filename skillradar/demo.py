"""Safe demonstration procedures for the university defense.

Every demo runs in an isolated SANDBOX (data/demo/<name>/): the real raw files are copied in,
ESCO is read from the real directory (read-only), and a separate SQLite file is used. The real
warehouse that the website shows is never modified. No demo calls the real Softon API: the
source-failure demo uses an in-memory mock server (httpx.MockTransport) that replays records
from the local raw snapshot.

Each demo returns a list of steps with the evidence that proves the claim.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import httpx

from .config import Settings
from .db import connect
from .gold.build import GOLD_TABLES
from .ingestion.softon_local import _snapshot_time, discover_files, read_envelope
from .pipeline.runner import run_backfill, run_pipeline

DEMOS = {
    "idempotency": "Run the pipeline twice on the same raw data: Bronze is not duplicated and Gold is identical.",
    "failed_validation": "Inject an invalid record: the quality gate blocks publication and the last valid Gold "
                         "stays published; a corrected record later recovers publication.",
    "backfill": "Backfill an empty date range (blocked: empty dataset), then the real snapshot date "
                "(published), then repeat it (no-op).",
    "source_failure": "Simulated Softon outage (mock server, no network): the run fails after retries, Gold is "
                      "kept; when the source recovers the next run succeeds and the watermark advances.",
}


def make_sandbox(base: Settings, name: str) -> Settings:
    root = base.data_dir / "demo" / name
    if root.exists():
        shutil.rmtree(root)
    (root / "raw").mkdir(parents=True)
    shutil.copytree(base.softon_raw_dir, root / "raw" / "softon")
    s = Settings(data_dir=root, esco_dir_override=base.esco_dir, softon_api_key_override="demo-mock-key")
    s.task_retry_delay_s = 0
    s.softon_backoff_s = 0
    s.ensure_dirs()
    return s


def gold_fingerprint(s: Settings) -> dict:
    conn = connect(s.db_path)
    try:
        h = hashlib.sha256()
        for t in GOLD_TABLES:
            for row in conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2"):
                h.update(json.dumps(list(row), ensure_ascii=False, default=str).encode())
        pub = conn.execute("SELECT version, vacancy_count FROM gold_publications ORDER BY version DESC LIMIT 1").fetchone()
        bronze = conn.execute("SELECT COUNT(*) FROM bronze_softon_jobs").fetchone()[0]
        alerts = conn.execute("SELECT COUNT(*) FROM ops_alerts WHERE level='error'").fetchone()[0]
        return {"gold_sha256": h.hexdigest()[:16], "gold_version": pub[0] if pub else None,
                "published_vacancies": pub[1] if pub else None, "bronze_rows": bronze, "error_alerts": alerts}
    finally:
        conn.close()


def _failed_checks(s: Settings, run_id: str) -> list[dict]:
    conn = connect(s.db_path)
    try:
        return [{"check": r[0], "failed": r[1], "sample": json.loads(r[2]).get("sample")} for r in conn.execute(
            "SELECT check_name, failed_count, sample_json FROM ops_dq_results WHERE run_id=? AND passed=0", (run_id,))]
    finally:
        conn.close()


def _step(steps: list, title: str, result: dict | None, s: Settings, expect: str,
          check: Callable[[dict], bool], vars: dict | None = None, **extra) -> dict:
    """Measure the sandbox state AFTER the step, then evaluate `check(state)` against it.
    `vars` carries the step parameters so the UI can render the step text in any language."""
    state = gold_fingerprint(s)
    steps.append({"step": len(steps) + 1, "title": title, "expected": expect, "ok": bool(check(state)), "vars": vars or {},
                  "run_status": result["status"] if result else None,
                  "run_id": result["run_id"] if result else None,
                  "tasks": result["tasks"] if result else None, "state": state, **extra})
    return state


def _later(minutes: int) -> str:
    """A timestamp guaranteed to be newer than every snapshot already in the sandbox (the newest version wins).
    Previously fixed dates were used, which silently broke the demo once real snapshots became newer."""
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _first_real_record(s: Settings) -> dict:
    files = sorted(p for p in s.softon_raw_dir.rglob("*.json") if not p.name.endswith(".meta.json"))
    doc = json.loads(files[0].read_text(encoding="utf-8-sig"))
    return dict(doc["data"][0])


def _write_snapshot(s: Settings, name: str, records: list[dict]) -> Path:
    path = s.snapshot_dir / "2026" / "11" / "25" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"data": records, "meta": {"next": None, "count": len(records),
                                                          "note": "INJECTED BY DEMO"}, "error": None},
                               ensure_ascii=False), encoding="utf-8")
    return path


# ----------------------------------------------------------------------------- demos
def demo_idempotency(base: Settings) -> list[dict]:
    s, steps = make_sandbox(base, "idempotency"), []
    r1 = run_pipeline(s, trigger="demo", sleep=lambda x: None)
    _step(steps, "First run on the real raw files", r1, s, "success; Gold v1 published", lambda st: r1["status"] == "success")
    before = steps[-1]["state"]
    r2 = run_pipeline(s, trigger="demo", sleep=lambda x: None)
    _step(steps, "Second run on the same raw files", r2, s,
          "success; 0 new Bronze rows; identical Gold content (new version number only)",
          lambda st: r2["status"] == "success" and st["gold_sha256"] == before["gold_sha256"]
          and st["bronze_rows"] == before["bronze_rows"] and st["gold_version"] == before["gold_version"] + 1,
          ingest=r2["outputs"].get("ingest_raw"))
    return steps


def demo_failed_validation(base: Settings) -> list[dict]:
    s, steps = make_sandbox(base, "failed_validation"), []
    r1 = run_pipeline(s, trigger="demo", sleep=lambda x: None)
    _step(steps, "Baseline run", r1, s, "success; Gold v1 published", lambda st: r1["status"] == "success")
    baseline = steps[-1]["state"]

    rec = _first_real_record(s)
    bad = dict(rec, salary_from=3000, salary_to=500, salary_currency="AZN",
               ingested_at=_later(1))      # newer version of a REAL record with an invalid range
    _write_snapshot(s, "demo_invalid.json", [bad])
    r2 = run_pipeline(s, trigger="demo", sleep=lambda x: None)
    _step(steps, f"Inject a newer version of {rec['id']} with salary_from 3000 > salary_to 500", r2, s,
          "blocked by valid_salary_ranges; Gold unchanged (same hash and version)",
          lambda st: r2["status"] == "blocked" and st["gold_sha256"] == baseline["gold_sha256"]
          and st["gold_version"] == baseline["gold_version"],
          failed_checks=_failed_checks(s, r2["run_id"]), vars={"record": rec["id"]})

    fixed = dict(rec, ingested_at=_later(2))    # source corrects the record (original values)
    _write_snapshot(s, "demo_corrected.json", [fixed])
    r3 = run_pipeline(s, trigger="demo", sleep=lambda x: None)
    _step(steps, "Source publishes a corrected version (newest version wins)", r3, s,
          "success; Gold v2 published",
          lambda st: r3["status"] == "success" and st["gold_version"] == baseline["gold_version"] + 1)
    return steps


def snapshot_dates(s: Settings) -> list[str]:
    """Distinct snapshot dates available in the raw landing zone (same rule as ingestion)."""
    out = set()
    for p in discover_files(s.softon_raw_dir):
        try:
            out.add(_snapshot_time(p, read_envelope(p))[0][:10])
        except (ValueError, json.JSONDecodeError):
            continue
    return sorted(out)


def demo_backfill(base: Settings) -> list[dict]:
    s, steps = make_sandbox(base, "backfill"), []
    dates = snapshot_dates(s)
    first_day, last_day = date.fromisoformat(dates[0]), date.fromisoformat(dates[-1])
    empty = ((first_day - timedelta(days=10)).isoformat(), (first_day - timedelta(days=1)).isoformat())
    r1 = run_backfill(s, *empty, trigger="demo", sleep=lambda x: None)
    _step(steps, f"Backfill {empty[0]}..{empty[1]} (no snapshots exist in this range)", r1, s,
          "blocked by volume_not_collapsed (empty dataset is never published)",
          lambda st: r1["status"] == "blocked" and st["gold_version"] is None,
          ingest=r1["outputs"].get("ingest_raw"), vars={"start": empty[0], "end": empty[1]}, available_dates=dates)
    real = (first_day.isoformat(), last_day.isoformat())
    r2 = run_backfill(s, *real, trigger="demo", sleep=lambda x: None)
    _step(steps, f"Backfill {real[0]}..{real[1]} (the real snapshot dates)", r2, s,
          "success; snapshots of those dates loaded and published",
          lambda st: r2["status"] == "success" and st["gold_version"] == 1,
          ingest=r2["outputs"].get("ingest_raw"), vars={"start": real[0], "end": real[1]}, available_dates=dates)
    first = steps[-1]["state"]
    r3 = run_backfill(s, *real, trigger="demo", sleep=lambda x: None)
    _step(steps, "Repeat the same backfill", r3, s, "success; 0 files loaded; identical Gold",
          lambda st: r3["status"] == "success" and st["gold_sha256"] == first["gold_sha256"]
          and r3["outputs"]["ingest_raw"]["files_new"] == 0,
          ingest=r3["outputs"].get("ingest_raw"))
    return steps


class _MockSofton:
    """In-memory Softon emulation: `failures` 503 responses, then the given page."""

    def __init__(self, page: list[dict], failures: int):
        self.page, self.failures, self.calls = page, failures, 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.failures > 0:
            self.failures -= 1
            return httpx.Response(503, json={"data": None, "meta": {}, "error": {"code": "unavailable"}})
        return httpx.Response(200, headers={"X-Quota-Limit": "100", "X-Quota-Used": "0"},
                              json={"data": self.page, "meta": {"next": None, "count": len(self.page)}, "error": None})


def demo_source_failure(base: Settings) -> list[dict]:
    s, steps = make_sandbox(base, "source_failure"), []
    r1 = run_pipeline(s, trigger="demo", sleep=lambda x: None)
    _step(steps, "Baseline run (local data)", r1, s, "success; Gold v1", lambda st: r1["status"] == "success")
    baseline = steps[-1]["state"]

    down = _MockSofton([], failures=10**6)
    r2 = run_pipeline(s, live=True, trigger="demo", sleep=lambda x: None,
                      params={"_transport": httpx.MockTransport(down.handler), "_sleep": lambda x: None, "max_pages": 1})
    _step(steps, "Softon outage: every request returns HTTP 503", r2, s,
          "fetch_live failed after retries; downstream skipped; Gold unchanged; alert raised",
          lambda st: r2["status"] == "failed" and st["gold_sha256"] == baseline["gold_sha256"]
          and st["gold_version"] == baseline["gold_version"] and st["error_alerts"] > baseline["error_alerts"],
          http_attempts=down.calls, error=r2["error"])

    sample = [dict(r, ingested_at=_later(1)) for r in
              json.loads(sorted(p for p in s.softon_raw_dir.rglob("*.json")
                                if not p.name.endswith(".meta.json"))[0].read_text(encoding="utf-8-sig"))["data"][:5]]
    up = _MockSofton(sample, failures=2)
    r3 = run_pipeline(s, live=True, trigger="demo", sleep=lambda x: None,
                      params={"_transport": httpx.MockTransport(up.handler), "_sleep": lambda x: None, "max_pages": 1})
    conn = connect(s.db_path)
    wm = conn.execute("SELECT watermark FROM ops_watermarks WHERE source='softon'").fetchone()
    conn.close()
    _step(steps, "Source recovers (2 transient 503s, then a page replaying 5 local records)", r3, s,
          "success after retries; raw snapshot written; watermark advanced; Gold republished",
          lambda st: r3["status"] == "success" and st["gold_version"] == baseline["gold_version"] + 1
          and st["bronze_rows"] > baseline["bronze_rows"], http_attempts=up.calls, watermark=wm[0] if wm else None,
          fetch=r3["outputs"].get("fetch_live"))
    return steps


RUNNERS: dict[str, Callable[[Settings], list[dict]]] = {
    "idempotency": demo_idempotency, "failed_validation": demo_failed_validation,
    "backfill": demo_backfill, "source_failure": demo_source_failure,
}


def run_demo(base: Settings, name: str) -> dict:
    if name not in RUNNERS:
        raise ValueError(f"unknown demo {name!r}; choose from {sorted(RUNNERS)}")
    steps = RUNNERS[name](base)
    return {"demo": name, "description": DEMOS[name], "passed": all(st["ok"] for st in steps),
            "sandbox": str((base.data_dir / "demo" / name).as_posix()), "steps": steps}
