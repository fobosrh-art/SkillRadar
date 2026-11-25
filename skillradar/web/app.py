"""SkillRadar web backend: JSON API under /api + the built React app (frontend/dist).

Data-exposure rules
  * Vacancy data is read ONLY from gold_* tables, which are replaced atomically and only after the
    blocking quality gate passes. Silver (candidate data, possibly invalid) is never served.
  * ESCO reference data (bronze_esco_*) is the official taxonomy, served read-only.
  * Ops metadata (runs, tasks, DQ results, alerts, API request log) contains no personal data.
  * Never served: API keys, raw files, Bronze payloads, contact fields.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ..config import PROJECT_ROOT, get_settings
from ..db import connect, init_db, table_counts
from ..demo import DEMOS
from ..ingestion.softon_api import get_state, remaining_budget, requests_used_this_month
from ..pipeline.scheduler import WebScheduler
from .admin import RUN_LOCK, OperationManager, is_local, require_admin
from .career import career_match, matching_jobs, roadmap
from . import labels as label_tr

DIST = PROJECT_ROOT / "frontend" / "dist"
ops = OperationManager(get_settings)
web_scheduler: WebScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if web_scheduler is not None:
        web_scheduler.stop()


app = FastAPI(title="SkillRadar", version="2.0", lifespan=lifespan,
              description="Baku job-market skill intelligence - published (Gold) data only")


def db():
    conn = connect(get_settings().db_path, check_same_thread=False)
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params)]


def one(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def _median(vals):
    vals = sorted(v for v in vals if v is not None)
    return round(statistics.median(vals), 2) if vals else None


def _quantile(vals, q):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return round(statistics.quantiles(vals, n=4, method="inclusive")[{0.25: 0, 0.75: 2}[q]], 2) if len(vals) > 1 else vals[0]


def publication(conn):
    p = one(conn, "SELECT * FROM gold_publications ORDER BY version DESC LIMIT 1")
    if p:
        p["row_counts"] = json.loads(p.pop("row_counts_json"))
        p["freshness"] = json.loads(p.pop("freshness_json"))
    return p


# ============================================================================ health / overview
@app.get("/api/health")
def health(conn=Depends(db)):
    p = publication(conn)
    return {"status": "ok" if p else "no_data", "gold_version": p["version"] if p else None,
            "published_at": p["published_at"] if p else None, "vacancies": p["vacancy_count"] if p else 0,
            "freshness": p["freshness"] if p else None, "demo": get_settings().demo_mode}


@app.get("/api/overview")
def overview(conn=Depends(db)):
    p = publication(conn)
    if not p:
        return {"published": False}
    v = one(conn, """SELECT COUNT(*) vacancies, COUNT(DISTINCT company_key) employers, COUNT(DISTINCT source) sources,
                            SUM(has_salary) with_salary, SUM(has_text) with_text,
                            SUM(skill_status='matched') with_skills, SUM(skill_status='no_text') no_text,
                            SUM(skill_status='no_match') no_match, SUM(occupation_uri IS NOT NULL) with_occupation,
                            SUM(also_listed_on IS NOT NULL) with_mirrors
                     FROM gold_vacancies""")
    skills = one(conn, "SELECT COUNT(*) n FROM gold_skill_demand")["n"]
    matches = one(conn, "SELECT COUNT(*) n FROM gold_vacancy_skills")["n"]
    last_run = one(conn, "SELECT run_id, run_type, trigger, status, started_at, duration_s FROM ops_pipeline_runs "
                         "ORDER BY started_at DESC LIMIT 1")
    dq = rows(conn, "SELECT check_name, severity, passed FROM ops_dq_results WHERE run_id=(SELECT run_id FROM "
                    "ops_dq_results ORDER BY id DESC LIMIT 1)")
    salary = one(conn, "SELECT * FROM gold_salary_coverage WHERE scope='ALL'")
    return {
        "published": True, "publication": p,
        "kpis": {**v, "distinct_skills": skills, "skill_matches": matches,
                 "raw_records": one(conn, "SELECT COUNT(*) n FROM bronze_softon_jobs")["n"],
                 "duplicates_removed": one(conn, "SELECT COALESCE(SUM(duplicates_removed),0) n "
                                                 "FROM gold_source_summary")["n"]},
        "last_run": last_run,
        "quality": {"passed": sum(d["passed"] for d in dq), "total": len(dq)},
        "salary": salary,
        "top_skills": rows(conn, "SELECT skill_uri, skill_label, skill_type, vacancies, share_of_text_pct "
                                 "FROM gold_skill_demand ORDER BY vacancies DESC, skill_label LIMIT 10"),
        "sources": rows(conn, "SELECT source, source_name, vacancies, share_pct, with_salary, with_text "
                              "FROM gold_source_summary ORDER BY vacancies DESC"),
        "occupations": rows(conn, "SELECT occupation_uri, occupation_label, vacancies FROM gold_occupation_demand "
                                  "ORDER BY vacancies DESC LIMIT 8"),
        "companies": rows(conn, "SELECT company_name, vacancies, with_salary FROM gold_company_summary "
                                "ORDER BY vacancies DESC, company_key LIMIT 8"),
        "first_seen_trend": rows(conn, "SELECT day, vacancies FROM gold_publication_trend WHERE "
                                       "date_basis='first_seen_date' AND source='ALL' ORDER BY day"),
        "posted_trend": rows(conn, "SELECT day, vacancies FROM gold_publication_trend WHERE "
                                   "date_basis='posted_date' AND source='ALL' ORDER BY day"),
        "languages": rows(conn, "SELECT COALESCE(text_lang,'unknown') lang, COUNT(*) n FROM gold_vacancies "
                                "GROUP BY 1 ORDER BY n DESC"),
        "recent": rows(conn, "SELECT job_id, title, company_name, source_name, posted_at, salary_from, salary_to, "
                             "salary_currency, salary_period, skill_count, occupation_label FROM gold_vacancies "
                             "ORDER BY posted_at DESC, job_id LIMIT 8"),
    }


# ============================================================================ vacancies
VAC_LIST_COLS = ("job_id, source, source_name, title, company_name, company_key, employment_type, salary_from, salary_to, "
                 "salary_currency, salary_period, has_salary, posted_at, deadline_at, has_text, text_lang, "
                 "skill_status, skill_count, occupation_uri, occupation_label, url, also_listed_on")
SORTS = {"newest": "posted_at DESC NULLS LAST, job_id", "oldest": "posted_at ASC NULLS LAST, job_id",
         "salary": "COALESCE(salary_to, salary_from) DESC NULLS LAST, job_id",
         "salary_asc": "COALESCE(salary_from, salary_to) ASC NULLS LAST, job_id",
         "skills": "skill_count DESC, job_id"}
# "today" and "last N days" are evaluated in Baku time (UTC+4, no DST)
POSTED_WITHIN = {"today": 0, "3": 2, "7": 6, "30": 29}


def vacancy_filters(q=None, source=None, occupation=None, skill=None, employment_type=None, company=None,
                    has_salary=None, has_skills=None, posted_within=None, salary_min=None, salary_max=None,
                    salary_period=None, currency=None):
    """WHERE clause shared by the list and the counters, applied to the whole published dataset.

    Salary range semantics (overlap): a vacancy matches [min, max] when its published range overlaps it.
    A vacancy publishing only one bound is treated as that single value (from 800 -> 800; up to 1200 -> 1200).
    Vacancies without a salary never match a salary filter (missing is not zero)."""
    where, params = [], []
    if q:
        where.append("(title LIKE ? OR company_name LIKE ? OR description_text LIKE ? OR requirements_text LIKE ?)")
        params += [f"%{q}%"] * 4
    for col, val in (("source", source), ("occupation_uri", occupation), ("employment_type", employment_type),
                     ("company_key", company)):
        if val:
            where.append(f"{col} = ?")
            params.append(val)
    if skill:
        where.append("job_id IN (SELECT job_id FROM gold_vacancy_skills WHERE skill_uri = ?)")
        params.append(skill)
    if has_skills is not None:
        where.append("skill_count > 0" if has_skills else "skill_count = 0")
    if posted_within:
        if posted_within not in POSTED_WITHIN:
            raise HTTPException(400, "posted_within must be one of today, 3, 7, 30")
        where.append("posted_date >= date('now', '+4 hours', ?)")
        params.append(f"-{POSTED_WITHIN[posted_within]} days")
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        raise HTTPException(400, "salary_min must not be greater than salary_max")
    salary_filter = salary_min is not None or salary_max is not None or salary_period or currency
    if salary_filter or has_salary:
        where.append("has_salary = 1")
    elif has_salary is False:
        where.append("has_salary = 0")
    if salary_min is not None:
        where.append("COALESCE(salary_to, salary_from) >= ?")
        params.append(salary_min)
    if salary_max is not None:
        where.append("COALESCE(salary_from, salary_to) <= ?")
        params.append(salary_max)
    if salary_period == "unspecified":
        where.append("salary_period IS NULL")
    elif salary_period:
        where.append("salary_period = ?")
        params.append(salary_period)
    if currency:
        where.append("salary_currency = ?")
        params.append(currency)
    return (" WHERE " + " AND ".join(where)) if where else "", params


@app.get("/api/vacancies")
def vacancies(conn=Depends(db), q: str | None = None, source: str | None = None,
              occupation: str | None = None, skill: str | None = None, employment_type: str | None = None,
              company: str | None = None, has_salary: bool | None = None, has_skills: bool | None = None,
              posted_within: str | None = None, salary_min: float | None = Query(None, ge=0),
              salary_max: float | None = Query(None, ge=0), salary_period: str | None = None,
              currency: str | None = None, sort: str = "newest",
              page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    clause, params = vacancy_filters(q, source, occupation, skill, employment_type, company, has_salary, has_skills,
                                     posted_within, salary_min, salary_max, salary_period, currency)
    total = conn.execute(f"SELECT COUNT(*) FROM gold_vacancies{clause}", params).fetchone()[0]
    items = rows(conn, f"SELECT {VAC_LIST_COLS} FROM gold_vacancies{clause} ORDER BY {SORTS.get(sort, SORTS['newest'])} "
                       f"LIMIT ? OFFSET ?", params + [page_size, (page - 1) * page_size])
    for it in items:
        it["also_listed_on"] = json.loads(it["also_listed_on"]) if it["also_listed_on"] else []
    published = conn.execute("SELECT COUNT(*) FROM gold_vacancies").fetchone()[0]
    return {"total": total, "published_total": published, "page": page, "page_size": page_size, "items": items}


@app.get("/api/vacancies/facets")
def vacancy_facets(conn=Depends(db)):
    return {
        "sources": rows(conn, "SELECT source AS value, MIN(source_name) AS label, COUNT(*) n FROM gold_vacancies "
                              "GROUP BY source ORDER BY n DESC"),
        "employment_types": rows(conn, "SELECT employment_type AS value, COUNT(*) n FROM gold_vacancies "
                                       "WHERE employment_type IS NOT NULL GROUP BY 1 ORDER BY n DESC"),
        "occupations": rows(conn, "SELECT occupation_uri AS value, occupation_label AS label, COUNT(*) n "
                                  "FROM gold_vacancies WHERE occupation_uri IS NOT NULL GROUP BY 1 ORDER BY n DESC"),
        "skills": rows(conn, "SELECT skill_uri AS value, skill_label AS label, vacancies AS n FROM gold_skill_demand "
                             "ORDER BY vacancies DESC, skill_label"),
        "companies": rows(conn, "SELECT company_key AS value, MIN(company_name) AS label, COUNT(*) n FROM gold_vacancies "
                                "WHERE company_key IS NOT NULL GROUP BY 1 ORDER BY n DESC, label"),
        "salary_periods": rows(conn, "SELECT COALESCE(salary_period, 'unspecified') AS value, COUNT(*) n FROM gold_vacancies "
                                     "WHERE has_salary = 1 GROUP BY 1 ORDER BY n DESC"),
        "currencies": rows(conn, "SELECT salary_currency AS value, COUNT(*) n FROM gold_vacancies "
                                 "WHERE has_salary = 1 GROUP BY 1 ORDER BY n DESC"),
        "posted_range": one(conn, "SELECT MIN(posted_date) min_date, MAX(posted_date) max_date, "
                                  "SUM(posted_date IS NULL) without_date, date('now', '+4 hours') today_baku "
                                  "FROM gold_vacancies"),
    }


@app.get("/api/vacancies/{job_id}")
def vacancy_detail(job_id: str, conn=Depends(db)):
    v = one(conn, "SELECT * FROM gold_vacancies WHERE job_id=?", (job_id,))
    if not v:
        raise HTTPException(404, "vacancy not found in the published dataset")
    v["also_listed_on"] = json.loads(v["also_listed_on"]) if v["also_listed_on"] else []
    v["skills"] = rows(conn, "SELECT skill_uri, skill_label, skill_type, field, start_pos, end_pos, matched_text, "
                             "label, label_type, lang, snippet FROM gold_vacancy_skills WHERE job_id=? "
                             "ORDER BY field, start_pos", (job_id,))
    return v


# ============================================================================ skills
@app.get("/api/skills")
def skills(conn=Depends(db), occupation: str | None = None, skill_type: str | None = None,
           q: str | None = None, limit: int = Query(1000, ge=1, le=5000)):
    base = "SELECT job_id FROM gold_vacancies WHERE (has_text=1 OR skill_count>0)"
    p: list = []
    if occupation:
        base += " AND occupation_uri=?"
        p.append(occupation)
    analysable = conn.execute(f"SELECT COUNT(*) FROM ({base})", p).fetchone()[0]
    where, wp = ["vs.job_id IN (" + base + ")"], list(p)
    if skill_type:
        where.append("vs.skill_type=?")
        wp.append(skill_type)
    if q:
        tr = label_tr.search_uris(get_settings().db_path, "skill", q)
        where.append(f"(vs.skill_label LIKE ?{' OR vs.skill_uri IN (' + ','.join('?' * len(tr)) + ')' if tr else ''})")
        wp += [f"%{q}%", *tr]
    items = rows(conn, f"""
        SELECT vs.skill_uri, MIN(vs.skill_label) skill_label, MIN(vs.skill_type) skill_type,
               COUNT(DISTINCT vs.job_id) vacancies, COUNT(*) mentions,
               GROUP_CONCAT(DISTINCT vs.lang) langs, GROUP_CONCAT(DISTINCT vs.label_type) label_types
        FROM gold_vacancy_skills vs WHERE {' AND '.join(where)}
        GROUP BY vs.skill_uri ORDER BY vacancies DESC, skill_label LIMIT ?""", wp + [limit])
    # The real number of distinct skills for the filters - independent of `limit` (display size).
    total_skills = conn.execute(f"SELECT COUNT(DISTINCT vs.skill_uri) FROM gold_vacancy_skills vs WHERE {' AND '.join(where)}",
                                wp).fetchone()[0]
    total_matches = conn.execute(f"SELECT COUNT(*) FROM gold_vacancy_skills vs WHERE {' AND '.join(where)}", wp).fetchone()[0]
    for it in items:
        it["share_pct"] = round(it["vacancies"] / analysable * 100, 1) if analysable else 0.0
    cov = one(conn, f"""SELECT COUNT(*) total, SUM(skill_status='matched') matched, SUM(skill_status='no_match') no_match,
                               SUM(skill_status='no_text') no_text FROM gold_vacancies
                        {'WHERE occupation_uri=?' if occupation else ''}""", tuple(p))
    by_label = rows(conn, f"""SELECT label_type, COUNT(*) n FROM gold_vacancy_skills
                              WHERE job_id IN ({base}) GROUP BY 1 ORDER BY n DESC""", p)
    by_lang = rows(conn, f"""SELECT lang, COUNT(*) n FROM gold_vacancy_skills
                             WHERE job_id IN ({base}) GROUP BY 1 ORDER BY n DESC""", p)
    by_type = rows(conn, f"""SELECT COALESCE(skill_type,'untyped') skill_type, COUNT(DISTINCT skill_uri) skills
                             FROM gold_vacancy_skills WHERE job_id IN ({base}) GROUP BY 1""", p)
    return {"analysable_vacancies": analysable, "total_skills": total_skills, "total_matches": total_matches,
            "returned": len(items), "coverage": cov, "by_label_type": by_label, "by_language": by_lang,
            "by_skill_type": by_type, "items": items,
            "method": "Dictionary matching of ESCO v1.2.0 labels and curated Azerbaijani/Russian/English aliases "
                      "(not a trained model). Share = vacancies mentioning the skill / vacancies with analysable text."}


@app.get("/api/skill")
def skill_detail(uri: str, conn=Depends(db)):
    s = one(conn, "SELECT skill_uri, preferred_label, skill_type, reuse_level, alt_labels, description "
                  "FROM bronze_esco_skills WHERE skill_uri=?", (uri,))
    if not s:
        raise HTTPException(404, "skill not in ESCO")
    s["alt_labels"] = [a for a in (s["alt_labels"] or "").split("\n") if a.strip()][:15]
    s["demand"] = one(conn, "SELECT vacancies, share_of_text_pct FROM gold_skill_demand WHERE skill_uri=?", (uri,))
    s["evidence"] = rows(conn, """
        SELECT vs.job_id, v.title, v.company_name, v.source_name, vs.field, vs.matched_text, vs.label,
               vs.label_type, vs.lang, vs.snippet
        FROM gold_vacancy_skills vs JOIN gold_vacancies v ON v.job_id=vs.job_id
        WHERE vs.skill_uri=? ORDER BY v.posted_at DESC LIMIT 60""", (uri,))
    s["matched_forms"] = rows(conn, "SELECT matched_text, label_type, lang, COUNT(*) n FROM gold_vacancy_skills "
                                    "WHERE skill_uri=? GROUP BY matched_text ORDER BY n DESC LIMIT 20", (uri,))
    s["co_occurring"] = rows(conn, """
        SELECT b.skill_uri, MIN(b.skill_label) skill_label, COUNT(DISTINCT b.job_id) vacancies
        FROM gold_vacancy_skills a JOIN gold_vacancy_skills b ON a.job_id=b.job_id AND b.skill_uri<>a.skill_uri
        WHERE a.skill_uri=? GROUP BY b.skill_uri ORDER BY vacancies DESC LIMIT 8""", (uri,))
    s["esco_occupations"] = one(conn, """SELECT SUM(relation_type='essential') essential, SUM(relation_type='optional') optional
                                         FROM bronze_esco_occupation_skills WHERE skill_uri=?""", (uri,))
    s["market_occupations"] = rows(conn, """
        SELECT v.occupation_uri, v.occupation_label, COUNT(DISTINCT v.job_id) vacancies
        FROM gold_vacancy_skills vs JOIN gold_vacancies v ON v.job_id=vs.job_id
        WHERE vs.skill_uri=? AND v.occupation_uri IS NOT NULL GROUP BY 1 ORDER BY vacancies DESC""", (uri,))
    return s


# ============================================================================ ESCO reference + career
@app.get("/api/esco/occupations")
def esco_occupations(conn=Depends(db), q: str | None = None, limit: int = Query(30, ge=1, le=100)):
    market = "(SELECT COUNT(*) FROM gold_vacancies v WHERE v.occupation_uri=o.occupation_uri)"
    if q:
        tr = label_tr.search_uris(get_settings().db_path, "occupation", q)
        extra = f" OR occupation_uri IN ({','.join('?' * len(tr))})" if tr else ""
        return rows(conn, f"""SELECT occupation_uri, preferred_label, isco_group, {market} market_vacancies
                              FROM bronze_esco_occupations o WHERE preferred_label LIKE ? OR alt_labels LIKE ?{extra}
                              ORDER BY market_vacancies DESC, (preferred_label LIKE ?) DESC, length(preferred_label)
                              LIMIT ?""", (f"%{q}%", f"%{q}%", *tr, f"{q}%", limit))
    return rows(conn, f"""SELECT occupation_uri, preferred_label, isco_group, {market} market_vacancies
                          FROM bronze_esco_occupations o WHERE occupation_uri IN
                          (SELECT DISTINCT occupation_uri FROM gold_vacancies WHERE occupation_uri IS NOT NULL)
                          ORDER BY market_vacancies DESC, preferred_label LIMIT ?""", (limit,))


@app.get("/api/esco/skills")
def esco_skills(conn=Depends(db), q: str = Query(..., min_length=2), limit: int = Query(20, ge=1, le=50)):
    tr = label_tr.search_uris(get_settings().db_path, "skill", q)
    extra = f" OR s.skill_uri IN ({','.join('?' * len(tr))})" if tr else ""
    return rows(conn, f"""SELECT s.skill_uri, s.preferred_label, s.skill_type,
                                COALESCE(d.vacancies, 0) baku_vacancies
                         FROM bronze_esco_skills s LEFT JOIN gold_skill_demand d ON d.skill_uri=s.skill_uri
                         WHERE s.preferred_label LIKE ? OR s.alt_labels LIKE ?{extra}
                         ORDER BY baku_vacancies DESC, (s.preferred_label LIKE ?) DESC, length(s.preferred_label)
                         LIMIT ?""", (f"%{q}%", f"%{q}%", *tr, f"{q}%", limit))


class CareerRequest(BaseModel):
    occupation_uri: str
    skill_uris: list[str] = Field(default_factory=list, max_length=300)


@app.post("/api/career/match")
def career_match_ep(body: CareerRequest, conn=Depends(db)):
    try:
        return career_match(conn, body.occupation_uri, body.skill_uris)
    except KeyError:
        raise HTTPException(404, "occupation not in ESCO")


@app.post("/api/career/jobs")
def career_jobs_ep(body: CareerRequest, conn=Depends(db)):
    try:
        return matching_jobs(conn, body.occupation_uri, body.skill_uris)
    except KeyError:
        raise HTTPException(404, "occupation not in ESCO")


class CompareRequest(BaseModel):
    occupation_uris: list[str] = Field(..., min_length=2, max_length=2)
    skill_uris: list[str] = Field(default_factory=list, max_length=300)


@app.post("/api/career/compare")
def career_compare_ep(body: CompareRequest, conn=Depends(db)):
    """Two occupations side by side: sample size, user coverage, top market skills, common skills and salary
    statistics per (currency, period) group - groups are never mixed."""
    out = []
    for uri in body.occupation_uris:
        try:
            m = career_match(conn, uri, body.skill_uris)
        except KeyError:
            raise HTTPException(404, "occupation not in ESCO")
        sal = rows(conn, """SELECT salary_currency currency, COALESCE(salary_period,'unspecified') period, COUNT(*) n,
                                   salary_from, salary_to FROM gold_vacancies
                            WHERE occupation_uri=? AND has_salary=1 GROUP BY job_id""", (uri,))
        groups = {}
        for r in sal:
            groups.setdefault((r["currency"], r["period"]), []).append(r)
        out.append({"occupation": m["occupation"], "vacancies": m["occupation_vacancies"],
                    "market_coverage": m["coverage"]["market"], "esco_essential_coverage": m["coverage"]["esco_essential"],
                    "top_skills": m["market_requirements"][:8],
                    "missing": [r for r in m["market_requirements"] if not r["user_has"]][:8],
                    "salary": [{"currency": c, "period": per, "vacancies": len(v),
                                "median_from": _median(x["salary_from"] for x in v), "median_to": _median(x["salary_to"] for x in v)}
                               for (c, per), v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]})
    full = [{r["skill_uri"]: r for r in career_match(conn, u, body.skill_uris)["market_requirements"]} for u in body.occupation_uris]
    common = [{"skill_uri": u, "label": full[0][u]["label"], "a": full[0][u]["vacancies"], "b": full[1][u]["vacancies"],
               "user_has": full[0][u]["user_has"]} for u in full[0] if u in full[1]]
    common.sort(key=lambda r: -(r["a"] + r["b"]))
    return {"occupations": out, "common_skills": common[:12]}


@app.post("/api/career/roadmap")
def roadmap_ep(body: CareerRequest, conn=Depends(db)):
    try:
        return roadmap(conn, body.occupation_uri, body.skill_uris)
    except KeyError:
        raise HTTPException(404, "occupation not in ESCO")


@app.get("/api/labels")
def esco_labels(conn=Depends(db)):
    """Local RU/AZ display labels for ESCO concepts (SkillRadar translations, not official ESCO ones) + coverage."""
    t = label_tr.translations(get_settings().db_path)
    gs = [r[0] for r in conn.execute("SELECT skill_uri FROM gold_skill_demand")]
    go = [r[0] for r in conn.execute("SELECT occupation_uri FROM gold_occupation_demand")]
    total_s = conn.execute("SELECT COUNT(*) FROM bronze_esco_skills").fetchone()[0]
    total_o = conn.execute("SELECT COUNT(*) FROM bronze_esco_occupations").fetchone()[0]
    return {
        "source": "SkillRadar local translations (not official ESCO translations)",
        "skill": {u: {"ru": v["ru"], "az": v["az"]} for u, v in t["skill"].items()},
        "occupation": {u: {"ru": v["ru"], "az": v["az"]} for u, v in t["occupation"].items()},
        "coverage": {
            "published_skills": {"translated": sum(u in t["skill"] for u in gs), "total": len(gs)},
            "published_occupations": {"translated": sum(u in t["occupation"] for u in go), "total": len(go)},
            "esco_skills": {"translated": len(t["skill"]), "total": total_s},
            "esco_occupations": {"translated": len(t["occupation"]), "total": total_o},
            "unresolved": t["unresolved"],
        },
    }


# ============================================================================ salary
@app.get("/api/salary")
def salary(conn=Depends(db), currency: str | None = None, period: str | None = None):
    vac = rows(conn, "SELECT job_id, title, source, source_name, occupation_uri, occupation_label, employment_type, "
                     "salary_from, salary_to, salary_currency, salary_period FROM gold_vacancies")
    total = len(vac)
    paid = [v for v in vac if v["salary_from"] is not None or v["salary_to"] is not None]
    for v in paid:
        v["period"] = v["salary_period"] or "unspecified"
    groups = []
    by_group = defaultdict(list)
    for v in paid:
        by_group[(v["salary_currency"], v["period"])].append(v)
    for (cur, per), items in sorted(by_group.items(), key=lambda kv: -len(kv[1])):
        groups.append({"currency": cur, "period": per, "vacancies": len(items),
                       "with_from": sum(i["salary_from"] is not None for i in items),
                       "with_to": sum(i["salary_to"] is not None for i in items),
                       "with_range": sum(i["salary_from"] is not None and i["salary_to"] is not None for i in items),
                       "median_from": _median(i["salary_from"] for i in items),
                       "median_to": _median(i["salary_to"] for i in items),
                       "median_midpoint": _median((i["salary_from"] + i["salary_to"]) / 2 for i in items
                                                  if i["salary_from"] is not None and i["salary_to"] is not None),
                       "p25_from": _quantile([i["salary_from"] for i in items], 0.25),
                       "p75_from": _quantile([i["salary_from"] for i in items], 0.75),
                       "min_from": min((i["salary_from"] for i in items if i["salary_from"] is not None), default=None),
                       "max_to": max((i["salary_to"] for i in items if i["salary_to"] is not None), default=None)})
    sel = next((g for g in groups if g["currency"] == currency and g["period"] == period), groups[0] if groups else None)
    detail = {}
    if sel:
        items = by_group[(sel["currency"], sel["period"])]
        floors = sorted(i["salary_from"] for i in items if i["salary_from"] is not None)
        width = 250 if (floors and floors[-1] <= 5000) else 500
        cap = None
        if len(floors) >= 10:
            cap = floors[int(len(floors) * 0.95) - 1]
        hist = Counter()
        for f in floors:
            b = int(f // width) * width
            if cap is not None and b > cap:
                b = int(cap // width) * width + width
                hist[("overflow", b)] += 1
            else:
                hist[("bin", b)] += 1
        bins = [{"from": b, "to": b + width, "vacancies": n, "overflow": kind == "overflow"}
                for (kind, b), n in sorted(hist.items(), key=lambda kv: kv[0][1])]

        def grouped(key, label_key):
            g = defaultdict(list)
            for i in items:
                if i[key]:
                    g[(i[key], i[label_key])].append(i)
            out = [{"key": k, "label": lbl, "vacancies": len(v), "median_from": _median(x["salary_from"] for x in v),
                    "median_to": _median(x["salary_to"] for x in v),
                    "min_from": min((x["salary_from"] for x in v if x["salary_from"] is not None), default=None),
                    "max_to": max((x["salary_to"] for x in v if x["salary_to"] is not None), default=None)}
                   for (k, lbl), v in g.items()]
            return sorted(out, key=lambda r: (-r["vacancies"], r["label"] or ""))
        detail = {"histogram": bins, "bin_width": width,
                  "by_occupation": grouped("occupation_uri", "occupation_label"),
                  "by_source": grouped("source", "source_name"),
                  "by_employment_type": grouped("employment_type", "employment_type"),
                  "vacancies": sorted(({k: i[k] for k in ("job_id", "title", "source_name", "occupation_uri", "occupation_label",
                                                         "salary_from", "salary_to")} for i in items),
                                      key=lambda i: -(i["salary_from"] or i["salary_to"] or 0))}
    coverage = []
    by_src = defaultdict(lambda: [0, 0])
    for v in vac:
        by_src[v["source_name"] or v["source"]][0] += 1
        by_src[v["source_name"] or v["source"]][1] += int(v["salary_from"] is not None or v["salary_to"] is not None)
    for src, (n, s) in sorted(by_src.items(), key=lambda kv: -kv[1][0]):
        coverage.append({"source": src, "vacancies": n, "with_salary": s, "coverage_pct": round(s / n * 100, 1)})
    return {"total_vacancies": total, "with_salary": len(paid),
            "coverage_pct": round(len(paid) / total * 100, 1) if total else 0.0,
            "groups": groups, "selected": sel, **detail, "coverage_by_source": coverage,
            "rules": ["Vacancies without a published salary are excluded, never counted as zero.",
                      "Currencies and pay periods are never mixed: every statistic is computed inside one "
                      "(currency, period) group. 'unspecified' = the source did not state a period.",
                      "Floors (salary_from) and ceilings (salary_to) are summarised separately; a midpoint is "
                      "only computed when both are published.",
                      "Amounts below 10 are treated as placeholders (not stated)."]}


# ============================================================================ pipeline / quality / sources
@app.get("/api/pipeline")
def pipeline(conn=Depends(db), limit: int = Query(50, ge=1, le=500)):
    runs = rows(conn, "SELECT run_id, run_type, trigger, status, started_at, finished_at, duration_s, params_json, error "
                      "FROM ops_pipeline_runs ORDER BY started_at DESC LIMIT ?", (limit,))
    tasks = defaultdict(list)
    for t in rows(conn, "SELECT run_id, task_name, status, attempts, duration_s, rows_out, error FROM ops_task_runs "
                        "ORDER BY id"):
        tasks[t["run_id"]].append(t)
    for r in runs:
        r["params"] = json.loads(r.pop("params_json") or "{}")
        r["tasks"] = tasks.get(r["run_id"], [])
        r["retries"] = sum(max(0, (t["attempts"] or 0) - 1) for t in r["tasks"])
    pubs = rows(conn, "SELECT version, run_id, published_at, vacancy_count, row_counts_json FROM gold_publications "
                      "ORDER BY version DESC")
    for p in pubs:
        p["row_counts"] = json.loads(p.pop("row_counts_json"))
    status_counts = Counter(r["status"] for r in rows(conn, "SELECT status FROM ops_pipeline_runs"))
    sched = one(conn, "SELECT * FROM ops_scheduler_state WHERE id=1")
    return {"runs": runs, "status_counts": dict(status_counts), "publications": pubs,
            "current_publication": publication(conn),
            "alerts": rows(conn, "SELECT id, run_id, level, message, created_at FROM ops_alerts ORDER BY id DESC LIMIT 50"),
            "layer_counts": {k: v for k, v in table_counts(conn).items() if k.startswith(("bronze_", "silver_", "gold_"))},
            "scheduler": {"state": sched, "web": web_scheduler.status() if web_scheduler else {"enabled": False}},
            "lock": one(conn, "SELECT run_id, acquired_at FROM ops_lock WHERE id=1")}


@app.get("/api/pipeline/runs/{run_id}")
def pipeline_run(run_id: str, conn=Depends(db)):
    run = one(conn, "SELECT * FROM ops_pipeline_runs WHERE run_id=?", (run_id,))
    if not run:
        raise HTTPException(404, "run not found")
    run["params"] = json.loads(run.pop("params_json") or "{}")
    tasks = rows(conn, "SELECT task_name, status, attempts, started_at, finished_at, duration_s, rows_out, details_json, "
                       "error FROM ops_task_runs WHERE run_id=? ORDER BY id", (run_id,))
    for t in tasks:
        d = json.loads(t.pop("details_json") or "{}")
        d.pop("snapshot_files", None)
        t["details"] = d
    metrics = rows(conn, "SELECT metric, value FROM ops_metrics WHERE run_id=? ORDER BY metric", (run_id,))
    return {"run": run, "tasks": tasks, "metrics": metrics,
            "quality": rows(conn, "SELECT check_name, severity, passed, checked_count, failed_count, sample_json "
                                  "FROM ops_dq_results WHERE run_id=? ORDER BY id", (run_id,)),
            "alerts": rows(conn, "SELECT level, message, created_at FROM ops_alerts WHERE run_id=?", (run_id,))}


CHECK_INFO = {
    "unique_normalized_ids": "IDs match '<source>:<native id>', prefix equals source, (source, native id) unique.",
    "non_empty_titles": "Every vacancy has a non-blank title.",
    "valid_dates": "posted_at parseable, on/after 2000-01-01 and not in the future; deadline parseable when present.",
    "valid_salary_ranges": "Only rows that state pay: 0 < amount <= 1,000,000, from <= to, known currency.",
    "normalized_baku_location": "Every vacancy normalises to city = Baku.",
    "no_contact_pii_in_text": "No e-mail address or phone number remains in any published text field.",
    "volume_not_collapsed": "Dataset not empty and at least 50% of the previous publication (catches partial loads).",
    "salary_coverage_info": "Informational: warns if fewer than 10% of vacancies state a salary.",
}


@app.get("/api/quality")
def quality(conn=Depends(db)):
    last = one(conn, "SELECT run_id FROM ops_dq_results ORDER BY id DESC LIMIT 1")
    checks = []
    if last:
        for c in rows(conn, "SELECT check_name, severity, passed, checked_count, failed_count, sample_json, created_at "
                            "FROM ops_dq_results WHERE run_id=? ORDER BY id", (last["run_id"],)):
            s = json.loads(c.pop("sample_json") or "{}")
            c.update(detail=s.get("detail"), sample=s.get("sample") or [], rule=CHECK_INFO.get(c["check_name"]))
            checks.append(c)
    history = rows(conn, """SELECT check_name, COUNT(*) runs, SUM(passed) passed, SUM(1-passed) failed
                            FROM ops_dq_results GROUP BY check_name""")
    runs = rows(conn, """SELECT r.run_id, r.started_at, r.status, SUM(d.passed) passed, COUNT(d.id) total
                         FROM ops_pipeline_runs r JOIN ops_dq_results d ON d.run_id=r.run_id
                         GROUP BY r.run_id ORDER BY r.started_at DESC""")
    issues = rows(conn, "SELECT field, issue, COUNT(*) n FROM silver_normalization_issues GROUP BY 1,2 ORDER BY n DESC")
    run = one(conn, "SELECT run_id, status, started_at FROM ops_pipeline_runs WHERE run_id=?",
              (last["run_id"],)) if last else None
    return {"run": run, "checks": checks, "history": history, "runs": runs, "normalization_issues": issues,
            "gate": "Blocking checks must all pass before Gold is replaced; otherwise the previous publication stays live."}


@app.get("/api/sources")
def sources(conn=Depends(db)):
    s = get_settings()
    files = rows(conn, "SELECT file_id, source, file_kind, path, substr(sha256,1,12) sha256, size_bytes, snapshot_at, "
                       "registered_at, record_count FROM bronze_raw_files ORDER BY registered_at")
    requests = rows(conn, "SELECT requested_at, status_code, records, quota_limit, quota_used, duration_ms, attempt, "
                          "params_json, error FROM ops_api_requests ORDER BY id DESC LIMIT 50")
    for r in requests:
        r["params"] = json.loads(r.pop("params_json") or "{}")
    state = get_state(conn)
    mirrors = rows(conn, "SELECT job_id, title, source_name, company_name, also_listed_on FROM gold_vacancies "
                         "WHERE also_listed_on IS NOT NULL")
    for m in mirrors:
        m["also_listed_on"] = json.loads(m["also_listed_on"])
    esco = {
        "occupations": one(conn, "SELECT COUNT(*) n FROM bronze_esco_occupations")["n"],
        "skills": one(conn, "SELECT COUNT(*) n FROM bronze_esco_skills")["n"],
        "relations": one(conn, "SELECT COUNT(*) n FROM bronze_esco_occupation_skills")["n"],
        "skill_types": rows(conn, "SELECT COALESCE(skill_type,'untyped') skill_type, COUNT(*) n FROM bronze_esco_skills "
                                  "GROUP BY 1 ORDER BY n DESC"),
        "relation_types": rows(conn, "SELECT relation_type, COUNT(*) n FROM bronze_esco_occupation_skills GROUP BY 1"),
        "dictionary_labels": one(conn, "SELECT COUNT(*) n FROM silver_skill_labels")["n"],
        "dictionary_by_type": rows(conn, "SELECT label_type, lang, COUNT(*) n FROM silver_skill_labels GROUP BY 1,2 "
                                         "ORDER BY n DESC"),
    }
    return {
        "softon": {
            "api_key_configured": bool(s.softon_api_key),
            "base_url": s.softon_base_url, "city": s.softon_city, "page_limit": s.softon_page_limit,
            "budget": {"monthly_budget": s.softon_monthly_budget, "used_this_month": requests_used_this_month(conn),
                       "remaining": remaining_budget(conn, s),
                       "last_quota": one(conn, "SELECT quota_limit, quota_used, requested_at FROM ops_api_requests "
                                               "WHERE quota_limit IS NOT NULL ORDER BY id DESC LIMIT 1")},
            "incremental": {"watermark": state.get("watermark"), "updated_at": state.get("updated_at"),
                            "resume_pending": bool(state.get("resume_cursor")),
                            "resume_params": json.loads(state["resume_params"]) if state.get("resume_params") else None},
            "files": files, "requests": requests,
            "sources": rows(conn, "SELECT * FROM gold_source_summary ORDER BY vacancies DESC"),
            "bronze_records": one(conn, "SELECT COUNT(*) n FROM bronze_softon_jobs")["n"],
            "distinct_ids": one(conn, "SELECT COUNT(DISTINCT job_id) n FROM bronze_softon_jobs")["n"],
            "published_vacancies": one(conn, "SELECT COUNT(*) n FROM gold_vacancies")["n"],
            "cross_source_duplicates": sum(len(m["also_listed_on"]) for m in mirrors), "mirrors": mirrors,
        },
        "esco": esco,
        "layers": {k: v for k, v in table_counts(conn).items() if k.startswith(("bronze_", "silver_", "gold_"))},
    }


# ============================================================================ admin (localhost only)
class FetchLiveRequest(BaseModel):
    confirm: bool = False
    max_pages: int = Field(1, ge=1, le=3)


class BackfillRequest(BaseModel):
    start: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class SchedulerRequest(BaseModel):
    enabled: bool
    interval_hours: float = Field(6, ge=0.05, le=168)
    run_now: bool = False


@app.get("/api/admin/status")
def admin_status(request: Request, conn=Depends(db)):
    s = get_settings()
    return {"local": is_local(request), "busy": RUN_LOCK.locked(), "current_operation": ops.current,
            "db_lock": one(conn, "SELECT run_id, acquired_at FROM ops_lock WHERE id=1"),
            "api_key_configured": bool(s.softon_api_key), "budget_remaining": remaining_budget(conn, s),
            "default_live_pages": 1, "demos": DEMOS,
            "scheduler": web_scheduler.status() if web_scheduler else {"enabled": False,
                                                                        "interval_hours": s.schedule_interval_hours}}


@app.get("/api/admin/operations", dependencies=[Depends(require_admin)])
def admin_operations(limit: int = Query(20, ge=1, le=100)):
    return ops.recent(limit)


@app.get("/api/admin/operations/{op_id}", dependencies=[Depends(require_admin)])
def admin_operation(op_id: str):
    op = ops.get(op_id)
    if not op:
        raise HTTPException(404, "operation not found")
    return op


@app.post("/api/admin/run", dependencies=[Depends(require_admin)], status_code=202)
def admin_run():
    return ops.submit("run", {})


@app.post("/api/admin/fetch-live", dependencies=[Depends(require_admin)], status_code=202)
def admin_fetch_live(body: FetchLiveRequest):
    if not body.confirm:
        raise HTTPException(400, "Live fetch requires explicit confirmation (confirm=true)")
    if not get_settings().softon_api_key:
        raise HTTPException(400, "SOFTON_API_KEY is not configured")
    return ops.submit("fetch_live", {"max_pages": body.max_pages})


@app.post("/api/admin/backfill", dependencies=[Depends(require_admin)], status_code=202)
def admin_backfill(body: BackfillRequest):
    if body.start > body.end:
        raise HTTPException(400, "start must be on or before end")
    return ops.submit("backfill", {"start": body.start, "end": body.end})


@app.post("/api/admin/demo/{name}", dependencies=[Depends(require_admin)], status_code=202)
def admin_demo(name: str):
    if name not in DEMOS:
        raise HTTPException(404, "unknown demo")
    return ops.submit(f"demo:{name}", {})


@app.post("/api/admin/scheduler", dependencies=[Depends(require_admin)])
def admin_scheduler(body: SchedulerRequest):
    global web_scheduler
    if web_scheduler is None:
        web_scheduler = WebScheduler(get_settings(), RUN_LOCK)
    if body.enabled:
        web_scheduler.start(body.interval_hours, run_now=body.run_now)
    else:
        web_scheduler.stop()
    return web_scheduler.status()


# ============================================================================ frontend (SPA)
@app.get("/api/{rest:path}", include_in_schema=False)
def api_not_found(rest: str):
    return JSONResponse({"detail": f"unknown API endpoint /api/{rest}"}, status_code=404)


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if not DIST.exists():
        return JSONResponse({"detail": "Frontend not built. Run setup.cmd (or: cd frontend && npm run build)."},
                            status_code=503)
    target = (DIST / full_path).resolve()
    if full_path and target.is_file() and DIST.resolve() in target.parents:
        return FileResponse(target)
    return FileResponse(DIST / "index.html")
