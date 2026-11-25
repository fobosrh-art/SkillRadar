"""Job Explorer filters, real skill counters and local ESCO label translations."""
import pytest
from fastapi.testclient import TestClient

from skillradar.pipeline.runner import run_pipeline
from skillradar.web.app import app

from .conftest import make_job, write_envelope


@pytest.fixture
def client(env):
    # salaries: 1) 800-1200 monthly  2) only from 1500  3) only up to 600  4) no salary
    write_envelope(env.snapshot_dir / "2026" / "11" / "25" / "sal.json", [
        make_job(41, id="boss_az:41", salary_from=800, salary_to=1200, salary_period="MONTH", ingested_at="2026-11-25T01:00:00Z"),
        make_job(42, id="boss_az:42", salary_from=1500, salary_to=None, ingested_at="2026-11-25T01:00:00Z"),
        make_job(43, id="boss_az:43", salary_from=None, salary_to=600, ingested_at="2026-11-25T01:00:00Z"),
        make_job(44, id="boss_az:44", salary_from=None, salary_to=None, salary_currency=None, ingested_at="2026-11-25T01:00:00Z"),
    ])
    assert run_pipeline(env, trigger="test", sleep=lambda s: None)["status"] == "success"
    return TestClient(app, client=("127.0.0.1", 1))


def ids(c, **p):
    return {i["job_id"] for i in c.get("/api/vacancies", params={**p, "page_size": 100}).json()["items"]}


def test_salary_range_uses_overlap_and_never_treats_missing_as_zero(client):
    got = ids(client, salary_min=1000, salary_max=1600)
    assert {"boss_az:41", "boss_az:42"} <= got            # 800-1200 overlaps; "from 1500" lies inside
    assert "boss_az:43" not in got and "boss_az:44" not in got   # "up to 600" below; no salary never matches
    assert "boss_az:44" not in ids(client, salary_max=5000)      # missing salary is not 0
    assert "boss_az:43" in ids(client, salary_max=700)
    assert ids(client, salary_period="MONTH") == {"boss_az:41"}
    assert "boss_az:41" not in ids(client, salary_period="unspecified")


def test_impossible_salary_range_is_rejected(client):
    assert client.get("/api/vacancies", params={"salary_min": 2000, "salary_max": 500}).status_code == 400


def test_filters_combine_and_counts_cover_whole_dataset(client):
    full = client.get("/api/vacancies", params={"page_size": 2}).json()
    assert full["total"] == full["published_total"] and len(full["items"]) == 2   # total is not the page length
    one = client.get("/api/vacancies", params={"has_salary": "true", "company": "company 41"}).json()
    assert one["total"] == 1
    assert client.get("/api/vacancies", params={"posted_within": "bad"}).status_code == 400
    facets = client.get("/api/vacancies/facets").json()
    assert facets["companies"] and facets["salary_periods"] and facets["posted_range"]["max_date"]


def test_skill_total_is_independent_of_display_limit(client):
    full = client.get("/api/skills").json()
    limited = client.get("/api/skills", params={"limit": 1}).json()
    assert limited["returned"] == 1 and limited["total_skills"] == full["total_skills"] >= 2


def test_local_labels_and_localised_search(client):
    labels = client.get("/api/labels").json()
    assert "not official" in labels["source"]
    assert labels["coverage"]["published_occupations"]["total"] >= 1
    assert any(v["ru"] == "бухгалтер" for v in labels["occupation"].values())
    found = [o["preferred_label"] for o in client.get("/api/esco/occupations", params={"q": "бухгалт"}).json()]
    assert "accountant" in found
    found_az = [s["preferred_label"] for s in client.get("/api/esco/skills", params={"q": "mühasibat uçotu"}).json()]
    assert "accounting" in found_az


def test_matching_jobs_and_compare(client):
    occs = {o["preferred_label"]: o["occupation_uri"] for o in client.get("/api/esco/occupations").json()}
    acc = occs["accountant"]
    skills = {s["skill_label"]: s["skill_uri"] for s in client.get("/api/skills").json()["items"]}
    none = client.post("/api/career/jobs", json={"occupation_uri": acc, "skill_uris": []}).json()
    assert none["items"] and all(i["coverage_pct"] == 0 for i in none["items"])        # no skills -> no fake score
    assert all(i["required"] > 0 for i in none["items"])                                # unscored vacancies not ranked
    one = client.post("/api/career/jobs", json={"occupation_uri": acc, "skill_uris": [skills["accounting"]]}).json()
    top = one["items"][0]
    assert top["coverage_pct"] == round(len(top["matched"]) / top["required"] * 100, 1) > 0
    cov = [i["coverage_pct"] for i in one["items"]]
    assert cov == sorted(cov, reverse=True)                                              # ranked by coverage
    cmp = client.post("/api/career/compare", json={"occupation_uris": [acc, occs["sales manager"]], "skill_uris": []}).json()
    assert len(cmp["occupations"]) == 2
    for o in cmp["occupations"]:
        assert len({(g["currency"], g["period"]) for g in o["salary"]}) == len(o["salary"])   # groups never mixed
    assert client.post("/api/career/compare", json={"occupation_uris": [acc], "skill_uris": []}).status_code == 422
