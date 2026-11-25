"""Web API tests: published-data-only reads, career logic, admin protection and operations."""
import time

import pytest
from fastapi.testclient import TestClient

from skillradar.db import connect, utcnow_iso
from skillradar.pipeline.runner import run_pipeline
from skillradar.web.app import app

from .conftest import make_job, write_envelope

ADMIN = {"X-SkillRadar-Admin": "1"}
LOCAL = ("127.0.0.1", 50000)


@pytest.fixture
def client(env):
    return TestClient(app, client=LOCAL)


@pytest.fixture
def published(env):
    assert run_pipeline(env, trigger="test", sleep=lambda s: None)["status"] == "success"
    return env


def test_no_data_before_first_publication(client):
    assert client.get("/api/health").json()["status"] == "no_data"
    assert client.get("/api/overview").json() == {"published": False}


def test_overview_and_lists_serve_gold_without_pii(client, published):
    ov = client.get("/api/overview").json()
    assert ov["kpis"]["vacancies"] == 6 and ov["kpis"]["raw_records"] == 7 and ov["kpis"]["duplicates_removed"] == 1
    assert ov["quality"] == {"passed": 8, "total": 8}
    body = " ".join(client.get(p).text for p in (
        "/api/overview", "/api/vacancies?page_size=100", "/api/skills", "/api/salary", "/api/sources",
        "/api/pipeline", "/api/quality"))
    for secret in ("hr@example.com", "person@gmail.com", "055 123 45 67", "111-22-33", "test-key-not-real"):
        assert secret not in body
    assert client.get("/api/sources").json()["softon"]["api_key_configured"] is True


def test_vacancy_search_filters_and_detail_with_evidence(client, published):
    res = client.get("/api/vacancies", params={"q": "Satış", "page_size": 10}).json()
    assert res["total"] == 1                       # holo_az mirror is published only via also_listed_on
    item = res["items"][0]
    assert item["job_id"] == "boss_az:2000" and item["also_listed_on"][0]["source"] == "holo_az"
    detail = client.get(f"/api/vacancies/{item['job_id']}").json()
    assert detail["skills"] and all(s["matched_text"] for s in detail["skills"])
    assert client.get("/api/vacancies/holo_az:1").status_code == 404
    paged = client.get("/api/vacancies", params={"page": 2, "page_size": 4}).json()
    assert paged["total"] == 6 and len(paged["items"]) == 2
    assert client.get("/api/vacancies", params={"has_salary": "true"}).json()["total"] == 6


def test_skills_salary_and_skill_detail(client, published):
    sk = client.get("/api/skills").json()
    assert sk["analysable_vacancies"] == 6 and sk["items"][0]["vacancies"] >= sk["items"][-1]["vacancies"]
    uri = next(i["skill_uri"] for i in sk["items"] if i["skill_label"] == "English")
    d = client.get("/api/skill", params={"uri": uri}).json()
    assert d["evidence"][0]["matched_text"] == "ingilis dili"
    sal = client.get("/api/salary").json()
    assert sal["with_salary"] == 6 and sal["groups"][0]["currency"] == "AZN"
    assert sal["groups"][0]["period"] == "unspecified" and sal["groups"][0]["median_from"] == 800


def test_career_match_separates_market_and_esco(client, published):
    occs = client.get("/api/esco/occupations").json()
    acc = next(o for o in occs if o["preferred_label"] == "accountant")
    assert acc["market_vacancies"] == 5
    skills = client.get("/api/skills").json()["items"]
    excel = next(i["skill_uri"] for i in skills if i["skill_label"] == "use spreadsheets software")
    m = client.post("/api/career/match", json={"occupation_uri": acc["occupation_uri"], "skill_uris": [excel]}).json()
    assert m["occupation_vacancies"] == 5
    assert any(r["skill_uri"] == excel and r["user_has"] for r in m["market_requirements"])
    assert [e["label"] for e in m["esco_essential"]] == ["accounting"]       # from the ESCO relation file
    assert m["coverage"]["esco_essential"] == {"matched": 0, "total": 1, "pct": 0.0}
    rm = client.post("/api/career/roadmap", json={"occupation_uri": acc["occupation_uri"], "skill_uris": [excel]}).json()
    labels = [i["label"] for i in rm["items"]]
    assert "use spreadsheets software" not in labels and labels[0] == "accounting"   # essential + market
    top = rm["items"][0]
    assert top["score"] == sum(top["components"].values()) and top["priority"] == "high"
    assert client.post("/api/career/match", json={"occupation_uri": "nope", "skill_uris": []}).status_code == 404


def test_admin_requires_localhost_header_and_same_origin(env, published):
    remote = TestClient(app, client=("10.0.0.5", 1234))
    assert remote.post("/api/admin/run", headers=ADMIN).status_code == 403
    local = TestClient(app, client=LOCAL)
    assert local.post("/api/admin/run").status_code == 403                                  # no CSRF header
    assert local.post("/api/admin/run", headers={**ADMIN, "Origin": "https://evil.example"}).status_code == 403
    assert local.post("/api/admin/fetch-live", headers=ADMIN, json={"max_pages": 1}).status_code == 400   # no confirm
    assert local.post("/api/admin/fetch-live", headers=ADMIN, json={"confirm": True, "max_pages": 9}).status_code == 422
    assert local.get("/api/admin/status").json()["local"] is True


def _wait(client, op_id, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        op = client.get(f"/api/admin/operations/{op_id}", headers=ADMIN).json()
        if op["status"] not in ("queued", "running"):
            return op
        time.sleep(0.1)
    raise AssertionError("operation did not finish")


def test_admin_run_operation_and_concurrency_guard(client, published):
    conn = connect(published.db_path)
    conn.execute("INSERT INTO ops_lock VALUES (1, 'cli-run', ?)", (utcnow_iso(),))      # CLI run in progress
    assert client.post("/api/admin/run", headers=ADMIN).status_code == 409
    conn.execute("DELETE FROM ops_lock")
    op = client.post("/api/admin/run", headers=ADMIN)
    assert op.status_code == 202
    done = _wait(client, op.json()["op_id"])
    assert done["status"] == "success" and done["run_id"]
    assert conn.execute("SELECT trigger FROM ops_pipeline_runs WHERE run_id=?", (done["run_id"],)).fetchone()[0] == "web"


def test_blocked_run_keeps_published_vacancies(client, published):
    before = client.get("/api/vacancies", params={"page_size": 100}).json()
    write_envelope(published.snapshot_dir / "2026" / "11" / "25" / "bad.json",
                   [make_job(1, **{"id": "boss_az:1001", "title": "", "ingested_at": "2026-11-25T09:00:00Z"})])
    op = client.post("/api/admin/run", headers=ADMIN).json()
    assert _wait(client, op["op_id"])["status"] == "blocked"
    assert client.get("/api/vacancies", params={"page_size": 100}).json() == before          # invalid Silver not served
    assert client.get("/api/quality").json()["run"]["status"] == "blocked"


def test_backfill_validation_and_spa_fallback(client, published):
    assert client.post("/api/admin/backfill", headers=ADMIN,
                       json={"start": "2026-11-25", "end": "2026-11-01"}).status_code == 400
    assert client.get("/api/does-not-exist").status_code == 404
