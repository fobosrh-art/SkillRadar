"""Data-quality gate between Silver and Gold.

A failed BLOCKING check stops publication: Gold keeps the last valid dataset.
WARNING checks are recorded and alerted but do not block.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import timedelta

from ..db import utcnow, utcnow_iso
from ..transform.normalize import KNOWN_CURRENCIES, parse_ts
from ..transform.pii import contains_pii

ID_PATTERN = re.compile(r"^[a-z0-9_]+:\S.*$")
MIN_VALID_DATE = "2000-01-01"
MAX_SALARY = 1_000_000


@dataclass
class CheckResult:
    name: str
    severity: str
    checked: int
    failed: int
    sample: list = field(default_factory=list)
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.failed == 0


class QualityGateFailed(RuntimeError):
    def __init__(self, failures: list[CheckResult]):
        self.failures = failures
        super().__init__("Blocking data-quality checks failed: " +
                         ", ".join(f"{f.name} ({f.failed} rows)" for f in failures))


def _vacancies(conn):
    return conn.execute("SELECT * FROM silver_vacancies").fetchall()


def check_unique_ids(rows) -> CheckResult:
    bad, seen, dupes = [], {}, []
    for r in rows:
        if not ID_PATTERN.match(r["job_id"] or "") or r["job_id"].startswith("__invalid__") \
                or r["job_id"].split(":", 1)[0] != r["source"]:
            bad.append(r["job_id"])
        key = (r["source"], r["native_id"])
        if key in seen:
            dupes.append(r["job_id"])
        seen[key] = r["job_id"]
    return CheckResult("unique_normalized_ids", "blocking", len(rows), len(bad) + len(dupes), (bad + dupes)[:10],
                       "id matches '<source>:<native>', prefix equals source, (source, native_id) unique")


def check_titles(rows) -> CheckResult:
    bad = [r["job_id"] for r in rows if not (r["title"] or "").strip()]
    return CheckResult("non_empty_titles", "blocking", len(rows), len(bad), bad[:10])


def check_dates(rows) -> CheckResult:
    """A PRESENT date must be valid; a MISSING date is not invalid (some employer career sites publish no
    posting date) - it is kept as NULL, counted and reported, never guessed."""
    upper = utcnow() + timedelta(days=1)
    bad, missing = [], 0
    for r in rows:
        if r["posted_at"] is None:
            missing += 1
        else:
            posted = parse_ts(r["posted_at"])
            if posted is None or r["posted_at"] < MIN_VALID_DATE or posted > upper:
                bad.append({"job_id": r["job_id"], "posted_at": r["posted_at"]})
                continue
        if r["deadline_at"] and parse_ts(r["deadline_at"]) is None:
            bad.append({"job_id": r["job_id"], "deadline_at": r["deadline_at"]})
    return CheckResult("valid_dates", "blocking", len(rows), len(bad), bad[:10],
                       f"posted_at parseable, >= {MIN_VALID_DATE}, <= now+1d when present "
                       f"({missing} without a source posting date, kept as missing); deadline parseable when present")


def check_salaries(rows) -> CheckResult:
    present = [r for r in rows if r["has_salary"]]
    bad = []
    for r in present:
        lo, hi = r["salary_from"], r["salary_to"]
        ok = all(v is None or 0 < v <= MAX_SALARY for v in (lo, hi))
        ok = ok and (lo is None or hi is None or lo <= hi)
        ok = ok and r["salary_currency"] in KNOWN_CURRENCIES
        if not ok:
            bad.append({"job_id": r["job_id"], "from": lo, "to": hi, "currency": r["salary_currency"]})
    return CheckResult("valid_salary_ranges", "blocking", len(present), len(bad), bad[:10],
                       "only rows that state a salary: 0 < amount <= 1e6, from <= to, known currency")


def check_location(rows) -> CheckResult:
    bad = [{"job_id": r["job_id"], "city": r["city"], "location_raw": r["location_raw"]}
           for r in rows if r["city"] != "Baku"]
    return CheckResult("normalized_baku_location", "blocking", len(rows), len(bad), bad[:10])


def check_no_pii(rows) -> CheckResult:
    bad = [r["job_id"] for r in rows
           if any(contains_pii(r[c]) for c in ("title", "description_text", "requirements_text", "company_name"))]
    return CheckResult("no_contact_pii_in_text", "blocking", len(rows), len(bad), bad[:10])


def check_volume(conn, rows, min_ratio: float) -> CheckResult:
    last = conn.execute("SELECT vacancy_count FROM gold_publications ORDER BY version DESC LIMIT 1").fetchone()
    canonical = sum(1 for r in rows if not r["is_duplicate"])
    failed = 0
    detail = f"canonical={canonical}"
    if canonical == 0:
        failed = 1
        detail += " (empty dataset)"
    elif last and canonical < last[0] * min_ratio:
        failed = 1
        detail += f" < {min_ratio:.0%} of last publication ({last[0]})"
    return CheckResult("volume_not_collapsed", "blocking", 1, failed, [] if not failed else [detail], detail)


def check_salary_coverage(rows) -> CheckResult:
    n = len(rows)
    with_sal = sum(r["has_salary"] for r in rows)
    pct = with_sal / n * 100 if n else 0
    return CheckResult("salary_coverage_info", "warning", n, 0 if pct >= 10 else 1, [],
                       f"{with_sal}/{n} vacancies state a salary ({pct:.1f}%)")


def run_checks(conn: sqlite3.Connection, run_id: str, min_volume_ratio: float = 0.5) -> list[CheckResult]:
    rows = _vacancies(conn)
    results = [check_unique_ids(rows), check_titles(rows), check_dates(rows), check_salaries(rows),
               check_location(rows), check_no_pii(rows), check_volume(conn, rows, min_volume_ratio),
               check_salary_coverage(rows)]
    now = utcnow_iso()
    conn.executemany(
        """INSERT INTO ops_dq_results(run_id, check_name, severity, passed, checked_count, failed_count,
               sample_json, created_at) VALUES (?,?,?,?,?,?,?,?)""",
        [(run_id, r.name, r.severity, int(r.passed), r.checked, r.failed,
          json.dumps({"sample": r.sample, "detail": r.detail}, ensure_ascii=False, default=str), now) for r in results])
    return results
