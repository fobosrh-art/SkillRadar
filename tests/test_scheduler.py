from skillradar.db import connect, init_db, utcnow_iso
from skillradar.pipeline.scheduler import scheduled_job


class FakeScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, func, trigger, **kw):
        self.jobs.append((trigger, kw))


def test_failed_scheduled_run_schedules_one_recovery_retry(env):
    conn = connect(env.db_path)
    init_db(conn)
    conn.execute("INSERT INTO ops_lock VALUES (1, 'someone-else', ?)", (utcnow_iso(),))   # forces a failure
    sched = FakeScheduler()
    res = scheduled_job(env, live=False, scheduler=sched, retry_minutes=1)
    assert res["status"] == "failed"
    assert len(sched.jobs) == 1 and sched.jobs[0][0] == "date" and sched.jobs[0][1]["kwargs"]["is_retry"] is True

    conn.execute("DELETE FROM ops_lock")
    retry = scheduled_job(**sched.jobs[0][1]["kwargs"])        # the retry itself succeeds
    assert retry["status"] == "success"
    trig = conn.execute("SELECT trigger FROM ops_pipeline_runs WHERE run_id=?", (retry["run_id"],)).fetchone()[0]
    assert trig == "scheduler_retry"


def test_successful_scheduled_run_schedules_nothing(env):
    sched = FakeScheduler()
    assert scheduled_job(env, live=False, scheduler=sched)["status"] == "success"
    assert sched.jobs == []
