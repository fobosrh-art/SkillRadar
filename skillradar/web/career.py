"""Career Match and Learning Roadmap - transparent rules, no ML.

Two kinds of evidence are kept strictly separate:
  * MARKET  - skills actually extracted from published Baku vacancies whose title maps to the
              target occupation (gold_vacancies + gold_vacancy_skills).
  * ESCO    - the occupation's essential / optional skills from the ESCO v1.2.0 taxonomy
              (bronze_esco_occupation_skills). This is a European reference profile, not Baku data.
A user skill counts as matched only on the exact ESCO skill URI (no fuzzy matching).
"""
from __future__ import annotations

import sqlite3

# Roadmap priority = transparent weighted sum (0-100), shown component by component in the UI.
W_OCC_MARKET = 50     # share of this occupation's Baku vacancies that mention the skill
W_ESCO = 30           # 1.0 essential, 0.5 optional, 0 not in ESCO profile
W_ALL_MARKET = 20     # demand across all analysable Baku vacancies, normalised to the top skill
ESCO_WEIGHT = {"essential": 1.0, "optional": 0.5}


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params)]


def occupation_profile(conn: sqlite3.Connection, occupation_uri: str) -> dict:
    occ = conn.execute("SELECT occupation_uri, preferred_label, isco_group, description FROM bronze_esco_occupations "
                       "WHERE occupation_uri=?", (occupation_uri,)).fetchone()
    if occ is None:
        raise KeyError(occupation_uri)
    esco = _rows(conn, """
        SELECT r.skill_uri, s.preferred_label AS label, s.skill_type, r.relation_type
        FROM bronze_esco_occupation_skills r JOIN bronze_esco_skills s ON s.skill_uri=r.skill_uri
        WHERE r.occupation_uri=? ORDER BY r.relation_type, s.preferred_label""", (occupation_uri,))
    occ_vacancies = conn.execute("SELECT COUNT(*) FROM gold_vacancies WHERE occupation_uri=?",
                                 (occupation_uri,)).fetchone()[0]
    market = _rows(conn, """
        SELECT vs.skill_uri, MIN(vs.skill_label) AS label, MIN(vs.skill_type) AS skill_type,
               COUNT(DISTINCT vs.job_id) AS vacancies
        FROM gold_vacancy_skills vs JOIN gold_vacancies v ON v.job_id=vs.job_id
        WHERE v.occupation_uri=? GROUP BY vs.skill_uri ORDER BY vacancies DESC, label""", (occupation_uri,))
    overall = {r["skill_uri"]: r for r in _rows(conn, "SELECT skill_uri, vacancies, share_of_text_pct FROM gold_skill_demand")}
    return {"occupation": dict(occ), "esco": esco, "occupation_vacancies": occ_vacancies,
            "market": market, "overall": overall}


def career_match(conn: sqlite3.Connection, occupation_uri: str, user_skills: list[str]) -> dict:
    p = occupation_profile(conn, occupation_uri)
    have = set(user_skills)
    esco_rel = {e["skill_uri"]: e["relation_type"] for e in p["esco"]}
    n_occ = p["occupation_vacancies"]

    def overall(uri):
        o = p["overall"].get(uri)
        return {"vacancies": o["vacancies"], "share_pct": o["share_of_text_pct"]} if o else {"vacancies": 0, "share_pct": 0.0}

    market = [{**m, "share_pct": round(m["vacancies"] / n_occ * 100, 1) if n_occ else 0.0,
               "user_has": m["skill_uri"] in have, "esco_relation": esco_rel.get(m["skill_uri"])} for m in p["market"]]
    essential = [{**e, "user_has": e["skill_uri"] in have, "baku": overall(e["skill_uri"])}
                 for e in p["esco"] if e["relation_type"] == "essential"]
    optional = [{**e, "user_has": e["skill_uri"] in have, "baku": overall(e["skill_uri"])}
                for e in p["esco"] if e["relation_type"] == "optional"]

    def cov(items):
        return {"matched": sum(i["user_has"] for i in items), "total": len(items),
                "pct": round(sum(i["user_has"] for i in items) / len(items) * 100, 1) if items else None}

    m_total = sum(m["vacancies"] for m in market)
    market_cov = {"matched": sum(m["user_has"] for m in market), "total": len(market),
                  "weighted_pct": round(sum(m["vacancies"] for m in market if m["user_has"]) / m_total * 100, 1)
                  if m_total else None}
    profile_uris = set(esco_rel) | {m["skill_uri"] for m in market}
    labels = {r[0]: r[1] for r in conn.execute(
        f"SELECT skill_uri, preferred_label FROM bronze_esco_skills WHERE skill_uri IN ({','.join('?' * len(have))})",
        tuple(have))} if have else {}
    return {
        "occupation": p["occupation"], "occupation_vacancies": n_occ,
        "market_requirements": market, "esco_essential": essential, "esco_optional": optional,
        "coverage": {"market": market_cov, "esco_essential": cov(essential), "esco_optional": cov(optional)},
        "other_user_skills": [{"skill_uri": u, "label": labels.get(u, u)} for u in sorted(have - profile_uris)],
        "method": ("Exact ESCO-URI matching. Market coverage is weighted by how many Baku vacancies of this "
                   "occupation mention each skill. ESCO coverage counts the essential/optional skills of the "
                   "European ESCO profile. The two kinds of evidence are kept separate."),
        "limitations": [
            f"Market evidence comes from {n_occ} published Baku vacanc{'y' if n_occ == 1 else 'ies'} mapped to this occupation."
            if n_occ else "No published Baku vacancy is mapped to this occupation yet, so there is no market evidence.",
            "Skills are extracted with dictionary matching (ESCO labels + curated AZ/RU aliases), not a trained model; "
            "a skill missing from a vacancy text is unknown, not proven absent.",
        ],
    }


def roadmap(conn: sqlite3.Connection, occupation_uri: str, user_skills: list[str]) -> dict:
    p = occupation_profile(conn, occupation_uri)
    have = set(user_skills)
    n_occ = p["occupation_vacancies"]
    occ_market = {m["skill_uri"]: m for m in p["market"]}
    esco_rel = {e["skill_uri"]: e for e in p["esco"]}
    max_all = max((o["vacancies"] for o in p["overall"].values()), default=0)

    candidates = (set(occ_market) | set(esco_rel)) - have
    items, omitted = [], 0
    for uri in candidates:
        e = esco_rel.get(uri)
        m = occ_market.get(uri)
        o = p["overall"].get(uri)
        rel = e["relation_type"] if e else None
        # optional ESCO skills with no Baku evidence at all add noise: counted, not listed
        if rel == "optional" and not m and not o:
            omitted += 1
            continue
        occ_share = (m["vacancies"] / n_occ) if (m and n_occ) else 0.0
        all_norm = (o["vacancies"] / max_all) if (o and max_all) else 0.0
        comp = {"occupation_market": round(W_OCC_MARKET * occ_share, 1),
                "esco_relation": round(W_ESCO * ESCO_WEIGHT.get(rel, 0.0), 1),
                "baku_market": round(W_ALL_MARKET * all_norm, 1)}
        score = round(sum(comp.values()), 1)
        reasons = []
        if m:
            reasons.append(f"mentioned in {m['vacancies']} of {n_occ} Baku vacancies for this occupation")
        if rel:
            reasons.append(f"ESCO {rel} skill for this occupation")
        if o:
            reasons.append(f"found in {o['vacancies']} Baku vacancies overall")
        items.append({"skill_uri": uri, "label": (e or m)["label"], "skill_type": (e or m)["skill_type"],
                      "esco_relation": rel, "occupation_vacancies": m["vacancies"] if m else 0,
                      "baku_vacancies": o["vacancies"] if o else 0, "score": score, "components": comp,
                      "priority": "high" if score >= 40 else "medium" if score >= 20 else "low",
                      "reasons": reasons})
    items.sort(key=lambda i: (-i["score"], i["label"]))
    if items:
        desc = {r[0]: r[1] for r in conn.execute(
            f"SELECT skill_uri, description FROM bronze_esco_skills WHERE skill_uri IN ({','.join('?' * len(items))})",
            tuple(i["skill_uri"] for i in items))}
        for i in items:
            i["description"] = (desc.get(i["skill_uri"]) or "").strip() or None
    return {"occupation": p["occupation"], "occupation_vacancies": n_occ, "items": items,
            "omitted_optional_without_evidence": omitted,
            "formula": {"occupation_market": f"{W_OCC_MARKET} x share of this occupation's Baku vacancies mentioning the skill",
                        "esco_relation": f"{W_ESCO} x (1.0 essential, 0.5 optional, 0 otherwise)",
                        "baku_market": f"{W_ALL_MARKET} x Baku vacancies mentioning the skill / top skill's count",
                        "tiers": "high >= 40, medium >= 20, low < 20"}}


def matching_jobs(conn: sqlite3.Connection, occupation_uri: str, user_skills: list[str], limit: int = 20) -> dict:
    """Published Baku vacancies of the chosen occupation ranked by coverage of their EXTRACTED skills.

    coverage = |user skills ∩ skills extracted from the vacancy| / |skills extracted from the vacancy|.
    Vacancies with no extracted skill cannot be scored and are counted separately (never ranked high).
    This is skill-list coverage only - not a hiring probability; experience, education and requirements
    not detected by the dictionary are not part of it.
    """
    if conn.execute("SELECT 1 FROM bronze_esco_occupations WHERE occupation_uri=?", (occupation_uri,)).fetchone() is None:
        raise KeyError(occupation_uri)
    have = set(user_skills)
    vac = _rows(conn, """SELECT job_id, title, company_name, source_name, url, posted_at, salary_from, salary_to,
                                salary_currency, salary_period, skill_count
                         FROM gold_vacancies WHERE occupation_uri=?""", (occupation_uri,))
    skills = {}
    for r in conn.execute("""SELECT DISTINCT vs.job_id, vs.skill_uri, vs.skill_label
                             FROM gold_vacancy_skills vs JOIN gold_vacancies v ON v.job_id=vs.job_id
                             WHERE v.occupation_uri=?""", (occupation_uri,)):
        skills.setdefault(r[0], {})[r[1]] = r[2]
    scored, unscored = [], 0
    for v in vac:
        req = skills.get(v["job_id"], {})
        if not req:
            unscored += 1
            continue
        matched = [{"skill_uri": u, "label": l} for u, l in sorted(req.items(), key=lambda x: x[1]) if u in have]
        missing = [{"skill_uri": u, "label": l} for u, l in sorted(req.items(), key=lambda x: x[1]) if u not in have]
        scored.append({**v, "required": len(req), "matched": matched, "missing": missing,
                       "coverage_pct": round(len(matched) / len(req) * 100, 1)})
    scored.sort(key=lambda x: (-x["coverage_pct"], -len(x["matched"]), -(x["required"]), x["posted_at"] or ""), reverse=False)
    return {"occupation_vacancies": len(vac), "scored": len(scored), "without_skills": unscored,
            "user_skills": len(have), "items": scored[:limit]}
