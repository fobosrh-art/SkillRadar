"""Skill and occupation extraction over Silver vacancies, with stored evidence."""
from __future__ import annotations

import logging
import re
import sqlite3

from ..db import transaction
from .matcher import LabelIndex, build_esco_entries, load_aliases

log = logging.getLogger(__name__)

# Single-token labels observed as false positives on the real corpus (see docs/skill_extraction.md):
#   "AR" = "Azərbaycan Respublikası" in Azerbaijani text, not augmented reality;
#   "IT" alt label maps to "computer technology" (too broad); "logging" is forestry in ESCO.
SKILL_STOPWORDS = {"ar", "it", "logging",
                   # final review on the 421-record corpus (2026-11-25), each seen in real text:
                   "history",      # "deployment/credit history" -> ESCO 'history' (academic subject)
                   "polish",       # verb "polish" -> ESCO language 'Polish'
                   "pos",          # "POS-terminal" -> 'blockchain consensus mechanisms'
                   "noc",          # "NOC environments" -> software configuration tools
                   "crafting",     # "crafting fast UIs" -> handicraft
                   "ecosystems",   # "vendor ecosystems" -> biology
                   "migration",    # "server migration" -> human migration
                   "energy",       # "energy and utilities sector" -> physics knowledge
                   "cfd"}          # "CFD" = contract for difference (finance) -> fluid dynamics
# ESCO alternative occupation labels that map real Baku titles to the wrong occupation:
#   "Planning Engineer" (project scheduling) -> 'land planner'; "Site Reliability Engineer" -> 'dependability
#   engineer'; "System Engineer" -> 'ICT network technician'; "QA Engineer" (software) -> 'quality engineer'.
OCCUPATION_EXCLUDED_LABELS = {"planning engineer", "reliability engineer", "system engineer", "qa engineer"}
OCCUPATION_STOPWORDS = {"manager", "specialist", "assistant", "operator", "consultant", "engineer", "expert",
                        "director", "officer", "worker", "head", "lead", "intern", "trainee", "coordinator",
                        "supervisor", "administrator", "analyst", "advisor", "adviser", "agent", "master"}


def build_skill_index(conn: sqlite3.Connection) -> tuple[LabelIndex, dict]:
    rows = conn.execute("SELECT skill_uri, preferred_label, alt_labels FROM bronze_esco_skills").fetchall()
    entries, stats = build_esco_entries(rows, SKILL_STOPWORDS)
    pref_to_uri = {r[1].lower(): r[0] for r in rows}
    aliases, rejected = load_aliases("skill_aliases.csv", pref_to_uri)
    stats.update(aliases_accepted=len(aliases), aliases_rejected=rejected)
    return LabelIndex(aliases + entries), stats   # aliases first: curated entries win on identical tokens


def build_occupation_index(conn: sqlite3.Connection) -> tuple[LabelIndex, dict]:
    rows = conn.execute("SELECT occupation_uri, preferred_label, alt_labels FROM bronze_esco_occupations").fetchall()
    entries, stats = build_esco_entries(rows, OCCUPATION_STOPWORDS, OCCUPATION_EXCLUDED_LABELS)
    pref_to_uri = {r[1].lower(): r[0] for r in rows}
    aliases, rejected = load_aliases("occupation_aliases.csv", pref_to_uri)
    stats.update(aliases_accepted=len(aliases), aliases_rejected=rejected)
    return LabelIndex(aliases + entries), stats


PLACEHOLDER_RE = re.compile(r"\[(?:EMAIL|PHONE)\]")


def blank_placeholders(text: str | None) -> str | None:
    """Replace redaction markers by spaces of equal length (keeps offsets, avoids matching 'Email')."""
    return PLACEHOLDER_RE.sub(lambda m: " " * len(m.group(0)), text) if text else text


def _snippet(text: str, start: int, end: int, width: int = 50) -> str:
    s = max(0, start - width)
    e = min(len(text), end + width)
    return ("…" if s else "") + text[s:e].replace("\n", " ") + ("…" if e < len(text) else "")


def extract_all(conn: sqlite3.Connection) -> dict:
    skill_index, skill_stats = build_skill_index(conn)
    occ_index, occ_stats = build_occupation_index(conn)
    if len(skill_index) == 0:
        raise RuntimeError("Skill dictionary is empty - load ESCO first (ingest-esco)")

    jobs = conn.execute("SELECT job_id, title, description_text, requirements_text, has_text FROM silver_vacancies").fetchall()
    skill_rows, occ_rows, status = [], [], []
    for j in jobs:
        seen = set()
        for field in ("title", "description_text", "requirements_text"):
            text = blank_placeholders(j[field])
            for m in skill_index.find(text):
                key = (m.entry.uri, field, m.start)
                if key in seen:
                    continue
                seen.add(key)
                skill_rows.append((j["job_id"], m.entry.uri, field.replace("_text", ""), m.start, m.end,
                                   m.matched_text, m.entry.label, m.entry.label_type, m.entry.lang,
                                   _snippet(text, m.start, m.end)))
        # occupation: longest label found in the title (one per vacancy)
        occ = occ_index.find(j["title"])
        if occ:
            best = max(occ, key=lambda m: (len(m.entry.tokens), m.entry.label_type == "preferred"))
            occ_rows.append((j["job_id"], best.entry.uri, best.matched_text, best.entry.label,
                             best.entry.label_type, best.entry.lang))
        st = "matched" if seen else ("no_match" if j["has_text"] else "no_text")
        status.append((st, j["job_id"]))

    with transaction(conn):
        conn.execute("DELETE FROM silver_job_skills")
        conn.execute("DELETE FROM silver_job_occupations")
        conn.execute("DELETE FROM silver_skill_labels")
        conn.executemany("INSERT INTO silver_job_skills VALUES (?,?,?,?,?,?,?,?,?,?)", skill_rows)
        conn.executemany("INSERT INTO silver_job_occupations VALUES (?,?,?,?,?,?)", occ_rows)
        conn.executemany("UPDATE silver_vacancies SET skill_status=? WHERE job_id=?", status)
        label_rows = {(" ".join(e.tokens) + ("*" if any(e.stems) else ""), e.uri): (e.label, e.label_type, e.lang)
                      for e in list(skill_index.exact.values()) + [x for v in skill_index.stemmed.values() for x in v]}
        conn.executemany("INSERT OR IGNORE INTO silver_skill_labels VALUES (?,?,?,?,?)",
                         [(k[0], k[1], *v) for k, v in label_rows.items()])
    counts = {s: sum(1 for x in status if x[0] == s) for s in ("matched", "no_match", "no_text")}
    result = {"skill_matches": len(skill_rows), "occupation_matches": len(occ_rows), "skill_status": counts,
              "skill_dictionary": {k: v for k, v in skill_stats.items() if k != "aliases_rejected"},
              "skill_aliases_rejected": skill_stats["aliases_rejected"],
              "occupation_aliases_rejected": occ_stats["aliases_rejected"]}
    log.info("extraction: %s", result)
    return result
