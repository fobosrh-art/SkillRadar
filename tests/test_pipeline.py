"""Integration tests: idempotency, quality gate blocking, source failure + recovery,
API client (pagination, retries, budget), backfill, locking."""
from __future__ import annotations

import json

import pytest

from skillradar.db import connect, init_db, utcnow_iso
from skillradar.ingestion.softon_api import BudgetExceeded, SourceError, fetch_jobs
from skillradar.pipeline.runner import run_backfill, run_pipeline

from .conftest import FakeSofton, make_job, write_envelope

NO_SLEEP = dict(sleep=lambda s: None)


def gold_snapshot(conn):
    return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in
            ("gold_source_summary", "gold_company_summary", "gold_skill_demand", "gold_salary_coverage",
             "gold_occupation_demand", "gold_publication_trend", "gold_vacancies", "gold_vacancy_skills")}


def counts(conn, *tables):
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


# ------------------------------------------------------------------ happy path + idempotency
def test_pipeline_publishes_gold_with_evidence(env):
    res = run_pipeline(env, trigger="test", **NO_SLEEP)
    assert res["status"] == "success", res
    conn = connect(env.db_path)
    c = counts(conn, "bronze_softon_jobs", "silver_vacancies", "silver_duplicate_links", "gold_publications")
    assert c == {"bronze_softon_jobs": 7, "silver_vacancies": 7, "silver_duplicate_links": 1, "gold_publications": 1}
    # cross-source duplicate holo_az:1 -> boss_az:2000 (earliest first_seen)
    link = conn.execute("SELECT canonical_job_id FROM silver_duplicate_links WHERE job_id='holo_az:1'").fetchone()
    assert link[0] == "boss_az:2000"
    # skills via multilingual aliases with evidence
    skills = {r[0]: r[1] for r in conn.execute("SELECT skill_label, vacancies FROM gold_skill_demand")}
    assert skills["use spreadsheets software"] == 5 and skills["English"] == 5 and skills["accounting"] == 5
    ev = conn.execute("SELECT matched_text FROM silver_job_skills WHERE skill_uri LIKE '%s-english'").fetchone()
    assert ev[0] == "ingilis dili"
    # PII never reaches Silver/Gold
    texts = " ".join(r[0] or "" for r in conn.execute("SELECT description_text FROM silver_vacancies"))
    assert "hr@example.com" not in texts and "055 123 45 67" not in texts and "[PHONE]" in texts
    assert "person@gmail.com" not in "".join(r[0] for r in conn.execute("SELECT payload_json FROM bronze_softon_jobs"))
    # processed storage export
    assert (env.processed_dir / "gold" / "gold_skill_demand.csv").exists()
    # run history + metrics
    tasks = conn.execute("SELECT task_name, status FROM ops_task_runs WHERE run_id=?", (res["run_id"],)).fetchall()
    assert all(t["status"] == "success" for t in tasks) and len(tasks) == 6
    assert conn.execute("SELECT COUNT(*) FROM ops_metrics WHERE run_id=? AND metric LIKE 'freshness.%'",
                        (res["run_id"],)).fetchone()[0] >= 3


def test_rerun_is_idempotent(env):
    run_pipeline(env, trigger="test", **NO_SLEEP)
    conn = connect(env.db_path)
    before = gold_snapshot(conn)
    c1 = counts(conn, "bronze_raw_files", "bronze_softon_jobs", "silver_vacancies", "silver_job_skills",
                "bronze_esco_skills")
    res = run_pipeline(env, trigger="test", **NO_SLEEP)
    assert res["status"] == "success"
    assert res["outputs"]["ingest_raw"]["files_already_loaded"] == 1 and res["outputs"]["ingest_raw"]["records_loaded"] == 0
    assert res["outputs"]["ingest_esco"]["skipped"] is True
    assert counts(conn, *c1.keys()) == c1
    assert gold_snapshot(conn) == before
    assert counts(conn, "gold_publications")["gold_publications"] == 2   # new version, identical content


# ------------------------------------------------------------------ quality gate
@pytest.mark.parametrize("bad, check", [
    (dict(salary_from=2000, salary_to=500), "valid_salary_ranges"),
    (dict(title="   "), "non_empty_titles"),
    (dict(location="Sumqayıt", city="Sumqayıt"), "normalized_baku_location"),
    (dict(posted_at="2031-01-01T00:00:00Z"), "valid_dates"),
    (dict(id="BROKEN-ID-WITHOUT-SOURCE"), "unique_normalized_ids"),
])
def test_invalid_data_blocks_publication_and_keeps_last_gold(env, bad, check):
    assert run_pipeline(env, trigger="test", **NO_SLEEP)["status"] == "success"
    conn = connect(env.db_path)
    before = gold_snapshot(conn)
    write_envelope(env.snapshot_dir / "2026" / "11" / "25" / "bad.json",
                   [make_job(99, **{"id": "boss_az:9999", "ingested_at": "2026-11-25T09:00:00Z", **bad})])
    res = run_pipeline(env, trigger="test", **NO_SLEEP)
    assert res["status"] == "blocked"
    assert res["tasks"]["quality_gate"] == "blocked" and res["tasks"]["publish_gold"] == "skipped"
    failed = {r[0] for r in conn.execute("SELECT check_name FROM ops_dq_results WHERE run_id=? AND passed=0",
                                         (res["run_id"],))}
    assert check in failed
    assert gold_snapshot(conn) == before                         # last valid dataset preserved
    assert counts(conn, "gold_publications")["gold_publications"] == 1
    assert conn.execute("SELECT COUNT(*) FROM ops_alerts WHERE run_id=? AND level='error'",
                        (res["run_id"],)).fetchone()[0] == 1
    assert (env.log_dir / "alerts.log").read_text(encoding="utf-8").count("Publication blocked") == 1


def test_missing_posting_date_is_published_not_guessed(env):
    """Regression (real data): employer career sites publish no posted_at. Missing != invalid."""
    write_envelope(env.snapshot_dir / "2026" / "11" / "25" / "employer.json",
                   [make_job(80, id="yapikredi:lawyer", source="yapikredi", posted_at=None,
                             ingested_at="2026-11-25T09:00:00Z")])
    res = run_pipeline(env, trigger="test", **NO_SLEEP)
    assert res["status"] == "success", res
    conn = connect(env.db_path)
    row = conn.execute("SELECT posted_at, posted_date FROM gold_vacancies WHERE job_id='yapikredi:lawyer'").fetchone()
    assert tuple(row) == (None, None)
    detail = json.loads(conn.execute("SELECT sample_json FROM ops_dq_results WHERE run_id=? AND check_name='valid_dates'",
                                     (res["run_id"],)).fetchone()[0])["detail"]
    assert "1 without a source posting date" in detail


def test_volume_collapse_blocks(env):
    run_pipeline(env, trigger="test", **NO_SLEEP)
    conn = connect(env.db_path)
    conn.execute("UPDATE gold_publications SET vacancy_count = 1000")   # pretend last publication was large
    res = run_pipeline(env, trigger="test", **NO_SLEEP)
    assert res["status"] == "blocked" and "volume_not_collapsed" in res["error"]


# ------------------------------------------------------------------ source failure and recovery
def test_source_failure_then_recovery(env):
    assert run_pipeline(env, trigger="test", **NO_SLEEP)["status"] == "success"
    conn = connect(env.db_path)
    before = gold_snapshot(conn)

    down = FakeSofton(pages=[[make_job(50, id="boss_az:5050")]], failures=100)
    res = run_pipeline(env, live=True, trigger="test", params={"_transport": down.transport, "_sleep": lambda s: None},
                       **NO_SLEEP)
    assert res["status"] == "failed" and res["tasks"]["fetch_live"] == "failed"
    assert all(res["tasks"][t] == "skipped" for t in ("ingest_raw", "build_silver", "publish_gold"))
    assert len(down.calls) == env.softon_max_retries + 1           # retried with backoff, then gave up
    assert gold_snapshot(conn) == before
    assert conn.execute("SELECT COUNT(*) FROM ops_alerts WHERE run_id=?", (res["run_id"],)).fetchone()[0] == 1

    # source recovers after two transient errors -> next run succeeds and publishes new data
    up = FakeSofton(pages=[[make_job(50, id="boss_az:5050", ingested_at="2026-11-25T08:00:00Z")],
                           [make_job(51, id="boss_az:5051", ingested_at="2026-11-25T08:30:00Z")]], failures=2)
    res2 = run_pipeline(env, live=True, trigger="test", params={"_transport": up.transport, "_sleep": lambda s: None},
                        **NO_SLEEP)
    assert res2["status"] == "success", res2
    assert res2["outputs"]["fetch_live"]["pages"] == 2
    assert conn.execute("SELECT COUNT(*) FROM silver_vacancies").fetchone()[0] == 9
    assert counts(conn, "gold_publications")["gold_publications"] == 2
    wm = conn.execute("SELECT watermark FROM ops_watermarks WHERE source='softon'").fetchone()[0]
    assert wm == "2026-11-25T08:30:00Z"


# ------------------------------------------------------------------ API client details
def _conn(env):
    conn = connect(env.db_path)
    init_db(conn)
    return conn


def test_api_client_pagination_incremental_params_and_snapshots(env):
    conn = _conn(env)
    conn.execute("INSERT INTO ops_watermarks(source, watermark, updated_at) VALUES ('softon','2026-11-24T12:00:00Z',?)",
                 (utcnow_iso(),))
    fake = FakeSofton(pages=[[make_job(1, ingested_at="2026-11-25T01:00:00Z")],
                             [make_job(2, ingested_at="2026-11-25T02:00:00Z")]])
    res = fetch_jobs(conn, env, "r1", max_pages=5, transport=fake.transport, sleep=lambda s: None)
    assert res.pages == 2 and res.exhausted
    first, second = fake.calls
    assert first.headers["Authorization"] == "Bearer test-key-not-real"
    assert first.url.params["city"] == "Bakı" and first.url.params["limit"] == "100"
    assert first.url.params["include"] == "bodies" and first.url.params["updated_after"] == "2026-11-24T12:00:00Z"
    assert first.url.params["order"] == "ingested_at" and second.url.params["cursor"] == "1"
    for f in res.snapshot_files:      # raw snapshot + sidecar written, never overwritten
        assert json.loads(open(f, encoding="utf-8").read())["data"]
    logged = conn.execute("SELECT params_json FROM ops_api_requests").fetchall()
    assert all("test-key-not-real" not in r[0] for r in logged)
    assert res.watermark_after == "2026-11-25T02:00:00Z"


def test_api_client_stops_at_max_pages(env):
    conn = _conn(env)
    fake = FakeSofton(pages=[[make_job(i, id=f"boss_az:{i}")] for i in range(5)])
    res = fetch_jobs(conn, env, "r1", max_pages=2, transport=fake.transport, sleep=lambda s: None)
    assert res.pages == 2 and not res.exhausted and len(fake.calls) == 2


def test_quota_exceeded_is_not_retried(env):
    conn = _conn(env)
    fake = FakeSofton(pages=[[make_job(1)]], failures=5, status=429, error_code="quota_exceeded")
    with pytest.raises(BudgetExceeded):
        fetch_jobs(conn, env, "r1", transport=fake.transport, sleep=lambda s: None)
    assert len(fake.calls) == 1


def test_local_budget_exhausted_refuses_request(env):
    conn = _conn(env)
    env.softon_monthly_budget = 0
    fake = FakeSofton(pages=[[make_job(1)]])
    with pytest.raises(BudgetExceeded):
        fetch_jobs(conn, env, "r1", transport=fake.transport, sleep=lambda s: None)
    assert fake.calls == []


def test_missing_api_key_refuses(env, monkeypatch):
    monkeypatch.delenv("SOFTON_API_KEY")
    with pytest.raises(SourceError, match="SOFTON_API_KEY"):
        fetch_jobs(_conn(env), env, "r1", transport=FakeSofton([[]]).transport)


# ------------------------------------------------------------------ backfill + lock
def test_backfill_only_loads_snapshots_in_range(env):
    write_envelope(env.snapshot_dir / "2026" / "11" / "20" / "s20.json",
                   [make_job(70, id="boss_az:7070", ingested_at="2026-11-20T10:00:00Z")])
    write_envelope(env.snapshot_dir / "2026" / "11" / "22" / "s22.json",
                   [make_job(71, id="boss_az:7171", ingested_at="2026-11-22T10:00:00Z")])
    res = run_backfill(env, "2026-11-20", "2026-11-21", trigger="test", **NO_SLEEP)
    assert res["status"] == "success"
    out = res["outputs"]["ingest_raw"]
    assert out["files_new"] == 1 and out["files_out_of_range"] == 2     # jobs_baku (11-24) and s22 excluded
    conn = connect(env.db_path)
    ids = {r[0] for r in conn.execute("SELECT job_id FROM silver_vacancies")}
    assert ids == {"boss_az:7070"}
    run = conn.execute("SELECT run_type, params_json FROM ops_pipeline_runs WHERE run_id=?", (res["run_id"],)).fetchone()
    assert run["run_type"] == "backfill" and json.loads(run["params_json"])["start"] == "2026-11-20"
    # re-running the same backfill is a no-op for Bronze
    res2 = run_backfill(env, "2026-11-20", "2026-11-21", trigger="test", **NO_SLEEP)
    assert res2["outputs"]["ingest_raw"]["files_new"] == 0


def test_concurrent_run_is_refused(env):
    conn = _conn(env)
    conn.execute("INSERT INTO ops_lock VALUES (1, 'other-run', ?)", (utcnow_iso(),))
    res = run_pipeline(env, trigger="test", **NO_SLEEP)
    assert res["status"] == "failed" and "already running" in res["error"]


def test_task_retry_recovers_from_transient_error(env, monkeypatch):
    from skillradar.pipeline import runner
    calls = {"n": 0}
    real = runner.build_silver

    def flaky(conn):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient disk error")
        return real(conn)

    monkeypatch.setattr(runner, "build_silver", flaky)
    res = run_pipeline(env, trigger="test", **NO_SLEEP)
    assert res["status"] == "success"
    conn = connect(env.db_path)
    attempts = conn.execute("SELECT attempts FROM ops_task_runs WHERE run_id=? AND task_name='build_silver'",
                            (res["run_id"],)).fetchone()[0]
    assert attempts == 2
