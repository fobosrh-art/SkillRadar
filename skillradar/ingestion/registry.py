"""Registry of raw files (Bronze landing zone). Files are identified by SHA-256,
so registering the same content twice is a no-op (idempotent ingestion)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from ..db import utcnow_iso


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel_path(path: Path, data_dir: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(data_dir).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def find_file(conn: sqlite3.Connection, sha: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM bronze_raw_files WHERE sha256 = ?", (sha,)).fetchone()


def register_file(conn: sqlite3.Connection, *, source: str, kind: str, path: Path, data_dir: Path,
                  sha: str, snapshot_at: str | None, record_count: int | None, run_id: str | None,
                  request: dict | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO bronze_raw_files(source, file_kind, path, sha256, size_bytes, snapshot_at,
                                        registered_at, record_count, run_id, request_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (source, kind, rel_path(path, data_dir), sha, Path(path).stat().st_size, snapshot_at,
         utcnow_iso(), record_count, run_id, json.dumps(request, ensure_ascii=False) if request else None))
    return cur.lastrowid
