"""Gold analytical tables. Built only from canonical (non-duplicate) Silver vacancies and
published atomically: all gold_* tables are replaced inside ONE transaction, so readers
see either the previous complete version or the new one - never a mix."""
from __future__ import annotations

import csv
import json
import logging
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from ..db import transaction, utcnow, utcnow_iso
from ..transform.normalize import parse_ts

log = logging.getLogger(__name__)

GOLD_TABLES = ["gold_source_summary", "gold_company_summary", "gold_occupation_demand", "gold_salary_coverage",
               "gold_skill_demand", "gold_publication_trend", "gold_vacancy_skills", "gold_vacancies"]
# delete order (children first) / insert order (parents first)
DELETE_ORDER = GOLD_TABLES
INSERT_ORDER = [t for t in GOLD_TABLES if t != "gold_vacancy_skills"] + ["gold_vacancy_skills"]


def _med(values):
    vals = [v for v in values if v is not None]
    return round(median(vals), 2) if vals else None


def _pct(a, b):
    return round(a / b * 100, 2) if b else 0.0


def compute_freshness(conn: sqlite3.Connection) -> dict:
    now = utcnow()
    row = conn.execute("""SELECT MAX(posted_at) p, MAX(source_ingested_at) i, MAX(snapshot_at) s
                          FROM silver_vacancies WHERE is_duplicate=0""").fetchone()
    out = {"computed_at": utcnow_iso()}
    for key, val in (("latest_posted_at", row["p"]), ("latest_source_ingested_at", row["i"]),
                     ("latest_snapshot_at", row["s"])):
        out[key] = val
        dt = parse_ts(val)
        out[key.replace("latest_", "") + "_age_hours"] = round((now - dt).total_seconds() / 3600, 2) if dt else None
    return out


def build_gold_rows(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    all_rows = conn.execute("SELECT * FROM silver_vacancies").fetchall()
    jobs = [r for r in all_rows if not r["is_duplicate"]]
    dup_by_source = Counter(r["source"] for r in all_rows if r["is_duplicate"])
    skills_by_job = defaultdict(set)
    for r in conn.execute("SELECT job_id, skill_uri FROM silver_job_skills"):
        skills_by_job[r[0]].add(r[1])
    total = len(jobs)
    out: dict[str, list[tuple]] = {}

    # --- sources
    by_source = defaultdict(list)
    for j in jobs:
        by_source[j["source"]].append(j)
    out["gold_source_summary"] = [
        (s, js[0]["source_name"], len(js), dup_by_source.get(s, 0), _pct(len(js), total),
         sum(j["has_salary"] for j in js), sum(j["has_text"] for j in js),
         sum(1 for j in js if skills_by_job.get(j["job_id"])),
         min((j["posted_at"] for j in js if j["posted_at"]), default=None),
         max((j["posted_at"] for j in js if j["posted_at"]), default=None),
         max((j["source_ingested_at"] or "") for j in js) or None)
        for s, js in sorted(by_source.items())]
    # sources that only contributed duplicates still appear (0 canonical vacancies)
    for s, n in dup_by_source.items():
        if s not in by_source:
            name = next(r["source_name"] for r in all_rows if r["source"] == s)
            out["gold_source_summary"].append((s, name, 0, n, 0.0, 0, 0, 0, None, None, None))

    # --- companies (vacancies without a stated company are not attributed to anyone)
    by_company = defaultdict(list)
    for j in jobs:
        if j["company_key"]:
            by_company[j["company_key"]].append(j)
    company_rows = []
    for key, js in by_company.items():
        name = Counter(j["company_name"] for j in js).most_common(1)[0][0]
        cur = Counter(j["salary_currency"] for j in js if j["salary_currency"])
        main_cur = cur.most_common(1)[0][0] if cur else None
        company_rows.append((key, name, len(js), len({j["source"] for j in js}), sum(j["has_salary"] for j in js),
                             _med(j["salary_from"] for j in js if j["salary_currency"] == main_cur),
                             main_cur, max((j["posted_at"] for j in js if j["posted_at"]), default=None)))
    out["gold_company_summary"] = sorted(company_rows, key=lambda r: (-r[2], r[0]))

    # --- occupations (ESCO match on title)
    occ_rows = conn.execute("""
        SELECT o.occupation_uri, e.preferred_label, e.isco_group, COUNT(*) n,
               GROUP_CONCAT(DISTINCT v.title) titles
        FROM silver_job_occupations o JOIN silver_vacancies v ON v.job_id=o.job_id AND v.is_duplicate=0
        JOIN bronze_esco_occupations e ON e.occupation_uri=o.occupation_uri
        GROUP BY o.occupation_uri ORDER BY n DESC""").fetchall()
    out["gold_occupation_demand"] = [(r[0], r[1], r[2], r[3], " | ".join((r[4] or "").split(",")[:5]))
                                     for r in occ_rows]

    # --- salary coverage (no currency conversion; only the dominant currency is aggregated)
    def salary_row(scope, js):
        cur = Counter(j["salary_currency"] for j in js if j["salary_currency"])
        main_cur = cur.most_common(1)[0][0] if cur else None
        sal = [j for j in js if j["has_salary"] and j["salary_currency"] == main_cur]
        return (scope, len(js), sum(j["has_salary"] for j in js),
                sum(1 for j in js if j["salary_from"] is not None and j["salary_to"] is not None),
                _pct(sum(j["has_salary"] for j in js), len(js)), main_cur,
                sum(1 for j in js if j["salary_period"]),
                min((j["salary_from"] for j in sal if j["salary_from"] is not None), default=None),
                _med(j["salary_from"] for j in sal), _med(j["salary_to"] for j in sal),
                max((j["salary_to"] for j in sal if j["salary_to"] is not None), default=None))
    out["gold_salary_coverage"] = [salary_row("ALL", jobs)] + [salary_row(s, js) for s, js in sorted(by_source.items())]

    # --- skills: share among vacancies that can be analysed (have text or any evidence)
    analysable = {j["job_id"] for j in jobs if j["has_text"] or skills_by_job.get(j["job_id"])}
    canonical_ids = {j["job_id"] for j in jobs}
    skill_rows = conn.execute("""
        SELECT s.skill_uri, e.preferred_label, e.skill_type, s.job_id, s.matched_text, s.lang, s.snippet
        FROM silver_job_skills s JOIN bronze_esco_skills e ON e.skill_uri=s.skill_uri
        ORDER BY s.skill_uri, s.job_id, s.field, s.start_pos""").fetchall()
    agg = {}
    for r in skill_rows:
        if r["job_id"] not in canonical_ids:
            continue
        a = agg.setdefault(r["skill_uri"], {"label": r["preferred_label"], "type": r["skill_type"], "jobs": set(),
                                            "langs": set(), "example": None})
        a["jobs"].add(r["job_id"])
        a["langs"].add(r["lang"])
        if a["example"] is None:
            a["example"] = (r["snippet"], r["job_id"])
    out["gold_skill_demand"] = sorted(
        [(uri, a["label"], a["type"], len(a["jobs"]), _pct(len(a["jobs"]), len(analysable)),
          ",".join(sorted(a["langs"])), a["example"][0], a["example"][1]) for uri, a in agg.items()],
        key=lambda r: (-r[3], r[1]))

    # --- trends: by source publication date and by first time the aggregator saw the posting
    trend = Counter()
    for j in jobs:
        for basis, day in (("posted_date", j["posted_date"]),
                           ("first_seen_date", (j["first_seen_at"] or "")[:10] or None)):
            if day:
                trend[(basis, day, "ALL")] += 1
                trend[(basis, day, j["source"])] += 1
    out["gold_publication_trend"] = [(*k, v) for k, v in sorted(trend.items())]

    # --- vacancy-level published data (canonical vacancies only; duplicates referenced as "also listed on")
    occ = {r["job_id"]: r for r in conn.execute("""
        SELECT o.job_id, o.occupation_uri, o.matched_text, e.preferred_label
        FROM silver_job_occupations o JOIN bronze_esco_occupations e ON e.occupation_uri=o.occupation_uri""")}
    mirrors = defaultdict(list)
    for r in all_rows:
        if r["is_duplicate"]:
            mirrors[r["canonical_job_id"]].append({"job_id": r["job_id"], "source": r["source"], "url": r["url"]})
    out["gold_vacancies"] = [
        (j["job_id"], j["source"], j["source_name"], j["title"], j["company_name"], j["company_key"], j["city"],
         j["employment_type"], j["job_function_raw"], j["career_level_raw"], j["salary_from"], j["salary_to"],
         j["salary_currency"], j["salary_period"], j["has_salary"], j["posted_at"], j["posted_date"],
         j["deadline_at"], j["first_seen_at"], j["url"], j["description_text"], j["requirements_text"],
         j["has_text"], j["text_lang"], j["skill_status"], len(skills_by_job.get(j["job_id"], ())),
         occ[j["job_id"]]["occupation_uri"] if j["job_id"] in occ else None,
         occ[j["job_id"]]["preferred_label"] if j["job_id"] in occ else None,
         occ[j["job_id"]]["matched_text"] if j["job_id"] in occ else None,
         json.dumps(mirrors[j["job_id"]], ensure_ascii=False) if mirrors.get(j["job_id"]) else None)
        for j in jobs]
    out["gold_vacancy_skills"] = [
        tuple(r) for r in conn.execute("""
            SELECT s.job_id, s.skill_uri, e.preferred_label, e.skill_type, s.field, s.start_pos, s.end_pos,
                   s.matched_text, s.label, s.label_type, s.lang, s.snippet
            FROM silver_job_skills s JOIN bronze_esco_skills e ON e.skill_uri=s.skill_uri
            JOIN silver_vacancies v ON v.job_id=s.job_id AND v.is_duplicate=0""")]
    return out


def publish_gold(conn: sqlite3.Connection, run_id: str, export_dir: Path | None = None) -> dict:
    tables = build_gold_rows(conn)
    freshness = compute_freshness(conn)
    vacancy_count = conn.execute("SELECT COUNT(*) FROM silver_vacancies WHERE is_duplicate=0").fetchone()[0]
    counts = {t: len(rows) for t, rows in tables.items()}
    with transaction(conn):
        for t in DELETE_ORDER:
            conn.execute(f"DELETE FROM {t}")
        for t in INSERT_ORDER:
            if tables[t]:
                ph = ",".join("?" * len(tables[t][0]))
                conn.executemany(f"INSERT INTO {t} VALUES ({ph})", tables[t])
        cur = conn.execute(
            "INSERT INTO gold_publications(run_id, published_at, vacancy_count, row_counts_json, freshness_json) "
            "VALUES (?,?,?,?,?)", (run_id, utcnow_iso(), vacancy_count, json.dumps(counts), json.dumps(freshness)))
        version = cur.lastrowid
    if export_dir:
        export_gold(conn, Path(export_dir))
    log.info("gold v%s published: %s", version, counts)
    return {"version": version, "vacancy_count": vacancy_count, "row_counts": counts, "freshness": freshness}


def export_gold(conn: sqlite3.Connection, export_dir: Path) -> None:
    """Processed storage: CSV copy of the currently published Gold tables (overwritten per publication)."""
    export_dir.mkdir(parents=True, exist_ok=True)
    for t in [t for t in GOLD_TABLES if t not in ("gold_vacancies", "gold_vacancy_skills")] + ["gold_publications"]:
        cur = conn.execute(f"SELECT * FROM {t}")
        with open(export_dir / f"{t}.csv", "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([d[0] for d in cur.description])
            w.writerows(cur.fetchall())
