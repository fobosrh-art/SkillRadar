"""Conservative cross-source duplicate detection.

Within a source, deduplication is exact by Softon id (latest snapshot version wins,
see silver.py). Across sources, two postings are linked ONLY if all hold:
  1. different sources (aggregators mirror each other, e.g. holo_az <-> boss_az)
  2. identical normalised title (non-empty)
  3. identical normalised company key (non-empty; postings without a company never merge)
  4. posted dates at most MAX_DAYS_APART apart
The canonical record is the one first seen earliest (tie: lexicographic job_id).
Duplicates are flagged, never deleted, so provenance stays visible.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

MAX_DAYS_APART = 3
RULE = "same_title+same_company+posted_within_3d+different_source"


@dataclass
class DedupCandidate:
    job_id: str
    source: str
    title_key: str | None
    company_key: str | None
    posted_date: str | None
    first_seen_at: str | None


def find_cross_source_duplicates(rows: list[DedupCandidate]) -> dict[str, tuple[str, dict]]:
    """Return {duplicate_job_id: (canonical_job_id, evidence)}."""
    groups: dict[tuple[str, str], list[DedupCandidate]] = defaultdict(list)
    for r in rows:
        if r.title_key and r.company_key and r.posted_date:
            groups[(r.title_key, r.company_key)].append(r)

    links: dict[str, tuple[str, dict]] = {}
    for (tkey, ckey), members in groups.items():
        if len({m.source for m in members}) < 2:
            continue
        members.sort(key=lambda m: (m.first_seen_at or "9999", m.job_id))
        canonical_for: list[DedupCandidate] = []
        for m in members:
            match = None
            for c in canonical_for:
                days = abs((date.fromisoformat(m.posted_date) - date.fromisoformat(c.posted_date)).days)
                if c.source != m.source and days <= MAX_DAYS_APART:
                    match = (c, days)
                    break
            if match:
                c, days = match
                links[m.job_id] = (c.job_id, {"title_key": tkey, "company_key": ckey, "days_apart": days,
                                              "sources": [c.source, m.source]})
            else:
                canonical_for.append(m)
    return links
