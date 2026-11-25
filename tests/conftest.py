"""Shared fixtures: an isolated data directory with a mini ESCO and small Softon files.
Tests never touch the real warehouse and never call the network."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import httpx
import pytest

from skillradar.config import Settings

SKILLS = [
    ("http://data.europa.eu/esco/skill/s-excel", "skill/competence", "use spreadsheets software", ""),
    ("http://data.europa.eu/esco/skill/s-english", "knowledge", "English", ""),
    ("http://data.europa.eu/esco/skill/s-acc", "knowledge", "accounting", ""),
    ("http://data.europa.eu/esco/skill/s-sql", "knowledge", "SQL", "structured query language"),
    ("http://data.europa.eu/esco/skill/s-sales", "knowledge", "sales activities", ""),
    ("http://data.europa.eu/esco/skill/s-team", "skill/competence", "work in teams", "teamwork"),
    ("http://data.europa.eu/esco/skill/s-pm", "knowledge", "project management", "security"),
]
OCCUPATIONS = [
    ("http://data.europa.eu/esco/occupation/o-acc", "2411", "accountant", "accounting officer"),
    ("http://data.europa.eu/esco/occupation/o-sm", "1221", "sales manager", ""),
]


def write_esco(esco_dir: Path) -> None:
    esco_dir.mkdir(parents=True, exist_ok=True)
    with open(esco_dir / "skills_en.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["conceptType", "conceptUri", "skillType", "reuseLevel", "preferredLabel", "altLabels",
                    "hiddenLabels", "status", "modifiedDate", "scopeNote", "definition", "inScheme", "description"])
        for uri, st, pref, alt in SKILLS:
            w.writerow(["KnowledgeSkillCompetence", uri, st, "cross-sector", pref, alt, "", "released", "", "", "", "", ""])
    with open(esco_dir / "occupations_en.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["conceptType", "conceptUri", "iscoGroup", "preferredLabel", "altLabels", "hiddenLabels",
                    "status", "modifiedDate", "regulatedProfessionNote", "scopeNote", "definition", "inScheme",
                    "description", "code"])
        for uri, isco, pref, alt in OCCUPATIONS:
            w.writerow(["Occupation", uri, isco, pref, alt, "", "released", "", "", "", "", "", "", isco + ".1"])
    with open(esco_dir / "occupationSkillRelations_en.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["occupationUri", "relationType", "skillType", "skillUri"])
        w.writerow([OCCUPATIONS[0][0], "essential", "knowledge", SKILLS[2][0]])
        w.writerow([OCCUPATIONS[1][0], "essential", "knowledge", SKILLS[4][0]])
        w.writerow([OCCUPATIONS[1][0], "optional", "knowledge", "http://data.europa.eu/esco/skill/missing"])


def make_job(i: int, **over) -> dict:
    job = {
        "id": f"boss_az:{1000 + i}", "source": "boss_az", "source_name": "Boss.az", "source_url": "https://boss.az",
        "title": "Mühasib", "company": {"name": f"Company {i} MMC", "slug": None}, "location": "Bakı",
        "remote": None, "employment_type": "Full-time", "job_function": None, "career_level": None,
        "salary_from": 800, "salary_to": 1200, "salary_currency": "AZN", "deadline_at": None,
        "posted_at": "2026-11-24T10:00:00Z", "url": f"https://boss.az/vacancies/{1000 + i}",
        "description": "Excel və ingilis dili biliyi. Mühasibat uçotu təcrübəsi. Əlaqə: 055 123 45 67, hr@example.com",
        "requirements": "Komandada işləmək bacarığı", "facts": {}, "first_seen_at": "2026-11-20T08:00:00Z",
        "times_seen": 1, "ingested_at": "2026-11-24T12:00:00Z", "active": True, "contact_email": "person@gmail.com",
        "contact_phone": "(050) 111-22-33", "salary_period": None, "city": "Bakı", "district": None, "country": None,
    }
    job.update(over)
    return job


def write_envelope(path: Path, jobs: list[dict], next_cursor=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"data": jobs, "meta": {"next": next_cursor, "count": len(jobs)}, "error": None},
                               ensure_ascii=False), encoding="utf-8-sig")
    return path


@pytest.fixture
def env(tmp_path, monkeypatch) -> Settings:
    data = tmp_path / "data"
    write_esco(data / "raw" / "esco")
    write_envelope(data / "raw" / "softon" / "jobs_baku.json", [make_job(i) for i in range(5)] + [
        make_job(10, id="holo_az:1", source="holo_az", source_name="Holo", title="Satış meneceri",
                 company={"name": "Doydum"}, description="Satış təcrübəsi, SQL"),
        make_job(11, id="boss_az:2000", title="Satış meneceri", company={"name": "Doydum MMC"},
                 first_seen_at="2026-11-19T08:00:00Z", description="Satış təcrübəsi"),
    ])
    monkeypatch.setenv("SKILLRADAR_DATA_DIR", str(data))
    monkeypatch.delenv("SKILLRADAR_DB_PATH", raising=False)
    monkeypatch.setenv("SOFTON_API_KEY", "test-key-not-real")
    s = Settings(data_dir=data)
    s.task_retry_delay_s = 0
    s.softon_backoff_s = 0
    s.ensure_dirs()
    return s


class FakeSofton:
    """httpx MockTransport emulating Softon pagination; `failures` = number of 503s before success."""

    def __init__(self, pages: list[list[dict]], failures: int = 0, status: int = 503, error_code: str = ""):
        self.pages, self.failures, self.status, self.error_code = pages, failures, status, error_code
        self.calls: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.failures > 0:
            self.failures -= 1
            return httpx.Response(self.status, json={"data": None, "meta": {}, "error": {"code": self.error_code}})
        cursor = request.url.params.get("cursor")
        idx = int(cursor) if cursor else 0
        nxt = str(idx + 1) if idx + 1 < len(self.pages) else None
        return httpx.Response(200, headers={"X-Quota-Limit": "100", "X-Quota-Used": str(len(self.calls))},
                              json={"data": self.pages[idx], "meta": {"next": nxt, "count": len(self.pages[idx])},
                                    "error": None})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)
