"""Load Softon raw JSON files (the provided export + timestamped API snapshots) into Bronze.

Raw files on disk are never modified. Each file is registered once (by SHA-256); its
records are copied into `bronze_softon_jobs` after PII anonymisation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from ..db import transaction, utcnow_iso
from ..transform.pii import anonymize_record
from .registry import find_file, register_file, sha256_file

log = logging.getLogger(__name__)


def discover_files(softon_raw_dir: Path) -> list[Path]:
    files = [p for p in Path(softon_raw_dir).rglob("*.json") if not p.name.endswith(".meta.json")]
    return sorted(files)


def read_envelope(path: Path) -> dict:
    # utf-8-sig: the provided export was written by PowerShell and starts with a BOM
    with open(path, encoding="utf-8-sig") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict) or not isinstance(doc.get("data"), list):
        raise ValueError(f"{path.name}: not a Softon envelope (expected object with 'data' list)")
    return doc


def _snapshot_time(path: Path, doc: dict) -> tuple[str, str]:
    """Return (snapshot_at, basis). Prefer the sidecar written by the live fetcher."""
    meta = path.with_name(path.stem + ".meta.json")
    if meta.exists():
        m = json.loads(meta.read_text(encoding="utf-8"))
        if m.get("fetched_at"):
            return m["fetched_at"], "fetch_sidecar"
    stamps = [r.get("ingested_at") for r in doc["data"] if isinstance(r, dict) and r.get("ingested_at")]
    if stamps:
        return max(stamps), "max_record_ingested_at"
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return mtime.strftime("%Y-%m-%dT%H:%M:%SZ"), "file_mtime"


def _in_range(snapshot_at: str, date_from: date | None, date_to: date | None) -> bool:
    d = date.fromisoformat(snapshot_at[:10])
    return (date_from is None or d >= date_from) and (date_to is None or d <= date_to)


def ingest_softon_files(conn: sqlite3.Connection, softon_raw_dir: Path, data_dir: Path, run_id: str | None,
                        date_from: date | None = None, date_to: date | None = None,
                        files: list[Path] | None = None) -> dict:
    stats = {"files_seen": 0, "files_new": 0, "files_already_loaded": 0, "files_out_of_range": 0,
             "files_rejected": 0, "records_loaded": 0, "pii_redactions": 0, "rejected": []}
    for path in files if files is not None else discover_files(softon_raw_dir):
        stats["files_seen"] += 1
        sha = sha256_file(path)
        if find_file(conn, sha):          # same content already in Bronze -> idempotent no-op
            stats["files_already_loaded"] += 1
            continue
        try:
            doc = read_envelope(path)
        except (ValueError, json.JSONDecodeError) as exc:
            stats["files_rejected"] += 1
            stats["rejected"].append(f"{path.name}: {exc}")
            log.warning("rejected raw file %s: %s", path, exc)
            continue
        snapshot_at, basis = _snapshot_time(path, doc)
        if not _in_range(snapshot_at, date_from, date_to):
            stats["files_out_of_range"] += 1
            continue

        loaded_at = utcnow_iso()
        with transaction(conn):
            file_id = register_file(
                conn, source="softon", kind="api_snapshot" if "snapshots" in path.parts else "local_export",
                path=path, data_dir=data_dir, sha=sha, snapshot_at=snapshot_at, record_count=len(doc["data"]),
                run_id=run_id, request={"snapshot_at_basis": basis, "meta": doc.get("meta")})
            rows = []
            for i, rec in enumerate(doc["data"]):
                if not isinstance(rec, dict):
                    rec = {"_invalid_record": rec}
                anon, n = anonymize_record(rec)
                payload = json.dumps(anon, ensure_ascii=False, sort_keys=True)
                job_id = rec.get("id") if isinstance(rec.get("id"), str) else None
                rows.append((file_id, i, job_id, rec.get("ingested_at"), payload,
                             hashlib.sha256(payload.encode("utf-8")).hexdigest(), n, loaded_at))
                stats["pii_redactions"] += n
            conn.executemany(
                """INSERT INTO bronze_softon_jobs(file_id, record_index, job_id, source_ingested_at,
                       payload_json, payload_sha256, pii_redactions, loaded_at) VALUES (?,?,?,?,?,?,?,?)""", rows)
        stats["files_new"] += 1
        stats["records_loaded"] += len(rows)
        log.info("loaded %s (%d records, snapshot_at=%s via %s)", path.name, len(rows), snapshot_at, basis)
    return stats


def reanonymize_bronze(conn: sqlite3.Connection) -> dict:
    """Re-apply the CURRENT anonymisation rules to stored Bronze payloads (after a rule improvement).
    Only rows whose payload changes are rewritten; raw files on disk are untouched."""
    changed, extra = 0, 0
    with transaction(conn):
        for row in conn.execute("SELECT bronze_id, payload_json, pii_redactions FROM bronze_softon_jobs").fetchall():
            anon, n = anonymize_record(json.loads(row["payload_json"]))
            payload = json.dumps(anon, ensure_ascii=False, sort_keys=True)
            if payload != row["payload_json"]:
                changed += 1
                extra += n
                conn.execute("UPDATE bronze_softon_jobs SET payload_json=?, payload_sha256=?, pii_redactions=pii_redactions+? "
                             "WHERE bronze_id=?", (payload, hashlib.sha256(payload.encode("utf-8")).hexdigest(), n,
                                                   row["bronze_id"]))
    return {"rows_rewritten": changed, "additional_redactions": extra}
