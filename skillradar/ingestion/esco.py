"""Import ESCO v1.2.0 CSVs (occupations, skills, occupation-skill relations) into Bronze."""
from __future__ import annotations

import csv
import logging
import sqlite3
import sys
from pathlib import Path

from ..db import transaction
from .registry import find_file, register_file, sha256_file

log = logging.getLogger(__name__)
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

FILES = {
    "occupations": "occupations_en.csv",
    "skills": "skills_en.csv",
    "relations": "occupationSkillRelations_en.csv",
}


def _rows(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh)


def load_esco(conn: sqlite3.Connection, esco_dir: Path, data_dir: Path, run_id: str | None = None,
              force: bool = False) -> dict:
    paths = {k: Path(esco_dir) / v for k, v in FILES.items()}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"ESCO files missing: {missing}")
    shas = {k: sha256_file(p) for k, p in paths.items()}

    if not force and all(find_file(conn, s) for s in shas.values()):
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
                  ("bronze_esco_occupations", "bronze_esco_skills", "bronze_esco_occupation_skills")}
        if counts["bronze_esco_skills"] > 0:
            log.info("ESCO already loaded (same file hashes) - skipping")
            return {"skipped": True, **counts}

    stats = {"skipped": False, "orphan_relations": 0}
    with transaction(conn):
        # dependent silver data is rebuilt by the pipeline afterwards
        for t in ("silver_job_skills", "silver_job_occupations", "silver_skill_labels",
                  "bronze_esco_occupation_skills", "bronze_esco_skills", "bronze_esco_occupations"):
            conn.execute(f"DELETE FROM {t}")
        file_ids = {}
        for k, p in paths.items():
            existing = find_file(conn, shas[k])
            file_ids[k] = existing["file_id"] if existing else register_file(
                conn, source="esco", kind="reference_csv", path=p, data_dir=data_dir, sha=shas[k],
                snapshot_at=None, record_count=None, run_id=run_id)

        occ = [(r["conceptUri"], r.get("code"), r.get("iscoGroup"), r["preferredLabel"], r.get("altLabels"),
                r.get("hiddenLabels"), r.get("status"), r.get("modifiedDate"), r.get("description"),
                file_ids["occupations"]) for r in _rows(paths["occupations"])]
        conn.executemany("INSERT INTO bronze_esco_occupations VALUES (?,?,?,?,?,?,?,?,?,?)", occ)

        skills = [(r["conceptUri"], r.get("skillType") or None, r.get("reuseLevel") or None, r["preferredLabel"],
                   r.get("altLabels"), r.get("hiddenLabels"), r.get("status"), r.get("modifiedDate"),
                   r.get("description"), file_ids["skills"]) for r in _rows(paths["skills"])]
        conn.executemany("INSERT INTO bronze_esco_skills VALUES (?,?,?,?,?,?,?,?,?,?)", skills)

        occ_uris = {o[0] for o in occ}
        skill_uris = {s[0] for s in skills}
        rels, seen = [], set()
        for r in _rows(paths["relations"]):
            key = (r["occupationUri"], r["skillUri"])
            if key[0] not in occ_uris or key[1] not in skill_uris:
                stats["orphan_relations"] += 1      # FK would fail; counted, not silently dropped
                continue
            if key in seen:
                continue
            seen.add(key)
            rels.append((key[0], key[1], r["relationType"], r.get("skillType"), file_ids["relations"]))
        conn.executemany("INSERT INTO bronze_esco_occupation_skills VALUES (?,?,?,?,?)", rels)

        for k, fid in file_ids.items():
            n = {"occupations": len(occ), "skills": len(skills), "relations": len(rels)}[k]
            conn.execute("UPDATE bronze_raw_files SET record_count=? WHERE file_id=?", (n, fid))

    stats.update(bronze_esco_occupations=len(occ), bronze_esco_skills=len(skills),
                 bronze_esco_occupation_skills=len(rels))
    log.info("ESCO loaded: %s", stats)
    return stats
