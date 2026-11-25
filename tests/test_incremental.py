"""No-skip incremental loading: tied ingested_at timestamps, resume cursor, invalid cursor fallback."""
import json

import httpx

from skillradar.db import connect, init_db, utcnow_iso
from skillradar.ingestion.softon_api import fetch_jobs, get_state, tie_safe_watermark
from skillradar.transform.normalize import parse_amount

from .conftest import make_job

T1, T2, T3 = "2026-11-25T01:00:00Z", "2026-11-25T02:00:00Z", "2026-11-25T03:00:00Z"


class KeysetServer:
    """Emulates Softon keyset pagination over `rows` (ascending ingested_at), honouring updated_after."""

    def __init__(self, rows, page_size=2, reject_cursor=False):
        self.rows, self.page_size, self.reject_cursor, self.calls = rows, page_size, reject_cursor, []

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(dict(req.url.params))
        if self.reject_cursor and "cursor" in req.url.params:
            return httpx.Response(400, json={"data": None, "meta": {}, "error": {"code": "invalid_request"}})
        after = req.url.params.get("updated_after")
        matching = [r for r in self.rows if not after or r["ingested_at"] > after]
        start = int(req.url.params.get("cursor", 0))
        page = matching[start:start + self.page_size]
        nxt = str(start + self.page_size) if start + self.page_size < len(matching) else None
        return httpx.Response(200, json={"data": page, "meta": {"next": nxt}, "error": None})


def _setup(env):
    conn = connect(env.db_path)
    init_db(conn)
    conn.execute("INSERT INTO ops_watermarks(source, watermark, updated_at) VALUES ('softon', ?, ?)",
                 ("2026-11-24T00:00:00Z", utcnow_iso()))
    return conn


def test_tie_safe_watermark():
    assert tie_safe_watermark([T1, T2, T2], has_next=True) == T1        # T2 batch may continue
    assert tie_safe_watermark([T2, T2], has_next=True) is None          # nothing provably complete
    assert tie_safe_watermark([T1, T2], has_next=False) == T2           # last page: everything complete


def test_tied_batch_across_pages_is_not_skipped(env):
    conn = _setup(env)
    # 5 rows; rows 2-5 share T2 (a batch), page size 2 -> the batch spans 2 pages
    rows = [make_job(1, id="boss_az:1", ingested_at=T1)] + \
           [make_job(i, id=f"boss_az:{i}", ingested_at=T2) for i in range(2, 6)]
    srv = KeysetServer(rows)
    r1 = fetch_jobs(conn, env, "r1", max_pages=1, transport=httpx.MockTransport(srv.handler), sleep=lambda s: None)
    st = get_state(conn)
    assert r1.pages == 1 and r1.resume_pending
    assert st["watermark"] == T1                 # NOT T2: the T2 batch is incomplete
    assert st["resume_cursor"] == "2" and json.loads(st["resume_params"])["updated_after"] == "2026-11-24T00:00:00Z"

    r2 = fetch_jobs(conn, env, "r2", max_pages=5, transport=httpx.MockTransport(srv.handler), sleep=lambda s: None)
    assert r2.resumed_from_cursor and r2.exhausted
    assert srv.calls[1]["cursor"] == "2" and srv.calls[1]["updated_after"] == "2026-11-24T00:00:00Z"
    ids = {r[0] for r in conn.execute("SELECT DISTINCT job_id FROM bronze_softon_jobs")}
    assert {f"boss_az:{i}" for i in range(1, 6)} <= ids                    # every row of the batch loaded
    st = get_state(conn)
    assert st["watermark"] == T2 and st["resume_cursor"] is None


def test_invalid_resume_cursor_falls_back_to_watermark(env):
    conn = _setup(env)
    conn.execute("UPDATE ops_watermarks SET resume_cursor='stale', resume_params=? WHERE source='softon'",
                 (json.dumps({"city": "Bakı", "limit": 100, "include": "bodies",
                              "updated_after": "2026-11-24T00:00:00Z", "order": "ingested_at"}),))
    srv = KeysetServer([make_job(1, id="boss_az:1", ingested_at=T3)], reject_cursor=True)
    res = fetch_jobs(conn, env, "r1", max_pages=2, transport=httpx.MockTransport(srv.handler), sleep=lambda s: None)
    assert srv.calls[0].get("cursor") == "stale" and "cursor" not in srv.calls[1]
    assert res.exhausted and get_state(conn)["watermark"] == T3


def test_salary_placeholder_and_bool_edge_cases():
    assert parse_amount(1) is None and parse_amount("1") is None      # observed placeholder value
    assert parse_amount(True) is None
    assert parse_amount(10) == 10.0 and parse_amount("850") == 850.0
