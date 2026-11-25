"""SQLite connection helpers and schema initialisation."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def connect(db_path: Path | str, check_same_thread: bool = True) -> sqlite3.Connection:
    """check_same_thread=False is used by the web app: FastAPI may open the per-request connection in one
    threadpool thread and run the endpoint in another. The connection is never shared between requests."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None,  # autocommit; explicit transactions
                           check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


# Columns added after the first release: (table, column, DDL type). Applied idempotently.
MIGRATIONS = [
    ("ops_watermarks", "resume_cursor", "TEXT"),
    ("ops_watermarks", "resume_params", "TEXT"),
]


def init_db(conn: sqlite3.Connection) -> None:
    for table, column, ddl in MIGRATIONS:   # upgrade existing databases before running the script
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')} if exists else set()
        if exists and column not in cols:
            conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}')
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))


@contextmanager
def transaction(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE ... COMMIT, ROLLBACK on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def table_counts(conn: sqlite3.Connection, prefix: str = "") -> dict[str, int]:
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ? AND name NOT LIKE 'sqlite_%' ORDER BY name",
        (prefix + "%",))]
    return {n: conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
