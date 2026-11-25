"""Synthetic demo dataset: isolated, clearly synthetic, passes the full pipeline, never uses the live API."""
import json

from fastapi.testclient import TestClient

from skillradar.config import Settings
from skillradar.demo_data import generate
from skillradar.pipeline.runner import run_pipeline
from skillradar.transform.pii import contains_pii
from skillradar.web.app import app


def test_demo_dataset_runs_end_to_end(tmp_path, monkeypatch):
    data = tmp_path / "data-demo"
    monkeypatch.setenv("SKILLRADAR_DEMO", "1")
    monkeypatch.setenv("SKILLRADAR_DATA_DIR", str(data))
    monkeypatch.setenv("SOFTON_API_KEY", "must-not-be-used")
    s = Settings(data_dir=data)
    assert s.demo_mode and s.softon_api_key is None             # demo never calls the live API

    info = generate(data)
    assert info["vacancies"] > 300
    doc = json.loads((data / "raw" / "softon" / "synthetic_jobs.json").read_text(encoding="utf-8"))
    assert "SYNTHETIC" in doc["meta"]["note"]
    for job in doc["data"]:
        assert job["url"].startswith("https://example.com/") and job["contact_email"] is None
        assert not contains_pii(job["description"] or "")
    assert generate(data)["skipped"] is True                     # idempotent, never overwrites silently

    s.task_retry_delay_s = 0
    res = run_pipeline(s, trigger="test", sleep=lambda x: None)
    assert res["status"] == "success", res

    client = TestClient(app, client=("127.0.0.1", 1))
    health = client.get("/api/health").json()
    assert health["demo"] is True and health["vacancies"] > 300
    assert client.get("/api/skills").json()["total_skills"] >= 30
    assert client.get("/api/sources").json()["softon"]["api_key_configured"] is False


def test_cli_refuses_to_generate_outside_demo_mode(tmp_path, monkeypatch):
    import pytest
    from skillradar.cli import main
    monkeypatch.delenv("SKILLRADAR_DEMO", raising=False)
    monkeypatch.setenv("SKILLRADAR_DATA_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as e:
        main(["generate-demo-data"])
    assert e.value.code == 2 and not (tmp_path / "raw").exists()


def test_failed_validation_demo_works_when_snapshots_are_recent(tmp_path, monkeypatch):
    """Regression: the demo injected records with fixed 2026-11-25 timestamps; with newer snapshots the injected
    record was treated as OLD and ignored, so the demo silently failed. Timestamps are now relative to 'now'."""
    from skillradar.demo import run_demo
    data = tmp_path / "data-demo"
    monkeypatch.setenv("SKILLRADAR_DEMO", "1")
    monkeypatch.setenv("SKILLRADAR_DATA_DIR", str(data))
    s = Settings(data_dir=data)
    generate(data)                                   # synthetic records are stamped with the current time
    s.task_retry_delay_s = 0
    assert run_pipeline(s, trigger="test", sleep=lambda x: None)["status"] == "success"
    res = run_demo(s, "failed_validation")
    assert res["passed"], res["steps"]
    assert [st["run_status"] for st in res["steps"]] == ["success", "blocked", "success"]
