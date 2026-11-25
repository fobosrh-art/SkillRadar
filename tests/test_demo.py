"""The defense demonstrations run in a sandbox and must never touch the real warehouse."""
import pytest

from skillradar.db import connect
from skillradar.demo import run_demo
from skillradar.pipeline.runner import run_pipeline


@pytest.mark.parametrize("name", ["idempotency", "failed_validation", "backfill", "source_failure"])
def test_demo_passes_and_leaves_main_db_untouched(env, name):
    run_pipeline(env, trigger="test", sleep=lambda s: None)
    conn = connect(env.db_path)
    before = conn.execute("SELECT COUNT(*) FROM ops_pipeline_runs").fetchone()[0], \
        conn.execute("SELECT MAX(version) FROM gold_publications").fetchone()[0]
    res = run_demo(env, name)
    assert res["passed"], res["steps"]
    after = conn.execute("SELECT COUNT(*) FROM ops_pipeline_runs").fetchone()[0], \
        conn.execute("SELECT MAX(version) FROM gold_publications").fetchone()[0]
    assert after == before
    assert (env.data_dir / "demo" / name / "warehouse" / "skillradar.db").exists()
