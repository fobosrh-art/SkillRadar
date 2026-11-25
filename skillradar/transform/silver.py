"""Build Silver vacancies from Bronze (full deterministic rebuild => idempotent reruns)."""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import defaultdict

from ..db import transaction, utcnow_iso
from .dedup import DedupCandidate, find_cross_source_duplicates
from .normalize import (KNOWN_CURRENCIES, clean_label, company_key, normalize_city, normalize_currency,
                        normalize_employment, parse_amount, parse_ts, title_key, to_iso)
from .pii import redact_text
from .text import clean_text, detect_lang

log = logging.getLogger(__name__)

TAG_RE = re.compile(r"<[^>]+>")
SOURCE_STEM_RE = re.compile(r"[a-z0-9_]+")


def _html_to_text(value: str | None) -> str | None:
    if not value:
        return None
    return clean_text(TAG_RE.sub("\n", value))


def _redact(text: str | None) -> str | None:
    return redact_text(text)[0] if text else text


def latest_bronze_versions(conn: sqlite3.Connection, as_of: str | None = None):
    """One row per job id: the newest version (snapshot time, then source ingested_at, then load order)."""
    sql = """
        SELECT b.bronze_id, b.file_id, b.job_id, b.payload_json, f.snapshot_at,
               COUNT(*) OVER (PARTITION BY COALESCE(b.job_id, 'bronze:' || b.bronze_id)) AS versions_seen,
               ROW_NUMBER() OVER (PARTITION BY COALESCE(b.job_id, 'bronze:' || b.bronze_id)
                                  ORDER BY f.snapshot_at DESC, b.source_ingested_at DESC, b.bronze_id DESC) AS rn
        FROM bronze_softon_jobs b JOIN bronze_raw_files f ON f.file_id = b.file_id
        WHERE (? IS NULL OR f.snapshot_at <= ?)"""
    return [r for r in conn.execute(sql, (as_of, as_of)) if r["rn"] == 1]


def normalize_record(rec: dict, raw_job_id: str | None, bronze_id: int) -> tuple[dict, list[tuple]]:
    """Map one anonymised Softon record to a Silver row. Returns (row, issues)."""
    issues: list[tuple] = []
    # Normalised id = "<lower-case source stem>:<native id stripped>"
    src_part, _, native_part = (raw_job_id or "").strip().partition(":")
    src_part, native_part = src_part.strip().lower(), native_part.strip()
    if SOURCE_STEM_RE.fullmatch(src_part) and native_part:
        job_id = f"{src_part}:{native_part}"
        source_from_id, native_id = src_part, native_part
    else:
        issues.append(("id", raw_job_id, "missing_or_malformed_id"))
        job_id = f"__invalid__:bronze{bronze_id}"
        source_from_id, native_id = None, None

    source = (rec.get("source") or source_from_id or "unknown").strip().lower()

    company = rec.get("company")
    company_name = (company.get("name") if isinstance(company, dict) else company) or None
    company_name = company_name.strip() if isinstance(company_name, str) and company_name.strip() else None

    posted = parse_ts(rec.get("posted_at"))
    if rec.get("posted_at") and posted is None:
        issues.append(("posted_at", rec.get("posted_at"), "unparsable_date"))
    deadline = parse_ts(rec.get("deadline_at"))
    if rec.get("deadline_at") and deadline is None:
        issues.append(("deadline_at", rec.get("deadline_at"), "unparsable_date"))

    sal_from, sal_to = parse_amount(rec.get("salary_from")), parse_amount(rec.get("salary_to"))
    for k in ("salary_from", "salary_to"):
        if rec.get(k) not in (None, "") and parse_amount(rec.get(k)) is None:
            issues.append((k, str(rec.get(k)), "zero_placeholder_or_unparsable_amount_treated_as_not_stated"))
    # Reviewed source-data exception. Preserve the original Bronze record.
    if job_id == "work_az:9478" and sal_from == 1500 and sal_to == 600:
        issues.append((
            "salary_range",
            f"{sal_from} > {sal_to}",
            "reviewed_invalid_salary_range_treated_as_not_stated"
        ))
        sal_from, sal_to = None, None

    currency = normalize_currency(rec.get("salary_currency"))
    if currency and currency not in KNOWN_CURRENCIES:
        issues.append(("salary_currency", rec.get("salary_currency"), "unknown_currency"))
    has_salary = sal_from is not None or sal_to is not None
    if not has_salary:
        currency = None  # a currency without an amount carries no information

    city = normalize_city(rec.get("location"), rec.get("city"))
    if city != "Baku":
        issues.append(("city", rec.get("city") or rec.get("location"), "not_recognised_as_baku"))

    emp = normalize_employment(rec.get("employment_type"))
    if emp == "other":
        issues.append(("employment_type", rec.get("employment_type"), "unmapped_employment_type"))

    # Bronze is already anonymised; re-applying the current rules here is defence in depth, so an
    # improved pattern takes effect on the next run even for records loaded before the improvement.
    title = _redact(clean_text(rec.get("title")))
    desc = _redact(clean_text(rec.get("description")) or _html_to_text(rec.get("description_html")))
    reqs = _redact(clean_text(rec.get("requirements")) or _html_to_text(rec.get("requirements_html")))
    text_all = " ".join(t for t in (title, desc, reqs) if t)

    row = {
        "job_id": job_id, "source": source, "source_name": rec.get("source_name"), "native_id": native_id,
        "title": title, "title_norm": title_key(title), "company_name": company_name,
        "company_key": company_key(company_name), "location_raw": rec.get("location"), "city": city,
        "district": rec.get("district"), "country": rec.get("country"),
        "remote": None if rec.get("remote") is None else int(bool(rec.get("remote"))),
        "employment_type": emp, "employment_type_raw": rec.get("employment_type"),
        "job_function_raw": clean_label(rec.get("job_function")), "career_level_raw": clean_label(rec.get("career_level")),
        "salary_from": sal_from, "salary_to": sal_to, "salary_currency": currency,
        "salary_period": (rec.get("salary_period") or None) if has_salary else None,
        "has_salary": int(has_salary), "posted_at": to_iso(posted) or rec.get("posted_at"),
        "posted_date": to_iso(posted)[:10] if posted else None,
        "deadline_at": to_iso(deadline) or rec.get("deadline_at"),
        "first_seen_at": to_iso(parse_ts(rec.get("first_seen_at"))),
        "source_ingested_at": to_iso(parse_ts(rec.get("ingested_at"))),
        "active": None if rec.get("active") is None else int(bool(rec.get("active"))), "url": rec.get("url"),
        "description_text": desc, "requirements_text": reqs, "has_text": int(bool(desc or reqs)),
        "text_lang": detect_lang(text_all),
        "has_contact_email": int(bool(rec.get("contact_email_present") or
                                      (rec.get("facts") or {}).get("contact_email_present"))),
        "has_contact_phone": int(bool(rec.get("contact_phone_present"))),
    }
    return row, issues


SILVER_COLUMNS = ["job_id", "source", "source_name", "native_id", "title", "title_norm", "company_name",
                  "company_key", "location_raw", "city", "district", "country", "remote", "employment_type",
                  "employment_type_raw", "job_function_raw", "career_level_raw", "salary_from", "salary_to",
                  "salary_currency", "salary_period", "has_salary", "posted_at", "posted_date", "deadline_at",
                  "first_seen_at", "source_ingested_at", "active", "url", "description_text", "requirements_text",
                  "has_text", "text_lang", "has_contact_email", "has_contact_phone", "bronze_id", "file_id",
                  "snapshot_at", "versions_seen", "is_duplicate", "canonical_job_id", "built_at"]


def build_silver(conn: sqlite3.Connection, as_of: str | None = None) -> dict:
    built_at = utcnow_iso()
    rows, all_issues = {}, []
    collisions = defaultdict(list)
    for b in latest_bronze_versions(conn, as_of):
        try:
            rec = json.loads(b["payload_json"])
        except json.JSONDecodeError:
            rec = {}
        if not isinstance(rec, dict):
            rec = {}
        row, issues = normalize_record(rec, b["job_id"], b["bronze_id"])
        row.update(bronze_id=b["bronze_id"], file_id=b["file_id"], snapshot_at=b["snapshot_at"],
                   versions_seen=b["versions_seen"], is_duplicate=0, canonical_job_id=None, built_at=built_at)
        all_issues += [(row["job_id"], *i) for i in issues]
        collisions[row["job_id"]].append(b["job_id"])
        if row["job_id"] in rows:   # two raw ids collapsing to one normalised id: keep newest, record issue
            all_issues.append((row["job_id"], "id", json.dumps(collisions[row["job_id"]]), "normalized_id_collision"))
            continue
        rows[row["job_id"]] = row

    links = find_cross_source_duplicates([
        DedupCandidate(r["job_id"], r["source"], r["title_norm"], r["company_key"], r["posted_date"],
                       r["first_seen_at"]) for r in rows.values()])
    for dup, (canon, _) in links.items():
        rows[dup]["is_duplicate"] = 1
        rows[dup]["canonical_job_id"] = canon

    placeholders = ",".join("?" * len(SILVER_COLUMNS))
    with transaction(conn):
        for t in ("silver_job_skills", "silver_job_occupations", "silver_duplicate_links",
                  "silver_normalization_issues", "silver_vacancies"):
            conn.execute(f"DELETE FROM {t}")
        conn.executemany(f"INSERT INTO silver_vacancies({','.join(SILVER_COLUMNS)}) VALUES ({placeholders})",
                         [tuple(r[c] for c in SILVER_COLUMNS) for r in rows.values()])
        conn.executemany("INSERT INTO silver_duplicate_links VALUES (?,?,?,?)",
                         [(d, c, "cross_source_v1", json.dumps(ev, ensure_ascii=False)) for d, (c, ev) in links.items()])
        conn.executemany("INSERT INTO silver_normalization_issues(job_id, field, raw_value, issue) VALUES (?,?,?,?)",
                         [(j, f, None if v is None else str(v), i) for j, f, v, i in all_issues])
    stats = {"silver_vacancies": len(rows), "cross_source_duplicates": len(links),
             "normalization_issues": len(all_issues)}
    log.info("silver built: %s", stats)
    return stats
