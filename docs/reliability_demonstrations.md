# Reliability demonstrations

Four demonstrations prove the pipeline's safety properties on demand. Each one copies the current warehouse and raw
files into an isolated sandbox (`<data dir>/demo/<name>/`), runs real pipeline executions there with a mocked HTTP
transport for the API, and compares a fingerprint of the published Gold tables before and after each step. The main
warehouse, its run history and the live API budget are never touched.

Run them from **Operations → Safe demonstrations** in the UI, or from the command line:

```bat
.venv\Scripts\python -m skillradar demo idempotency
.venv\Scripts\python -m skillradar demo failed_validation
.venv\Scripts\python -m skillradar demo backfill
.venv\Scripts\python -m skillradar demo source_failure
```

| Demo | Steps (run status) | What it proves |
|---|---|---|
| `idempotency` | run → run again (`success`, `success`) | Re-processing the same raw files adds no Bronze rows and leaves the Gold fingerprint identical. |
| `failed_validation` | baseline → inject a newer version of a record with an impossible salary range → source corrects it (`success`, `blocked`, `success`) | The quality gate blocks publication; the previous Gold stays live byte-for-byte and an alert is raised. The corrected record is published by the next run. |
| `backfill` | backfill a range with no snapshots → backfill the real snapshot dates → repeat the same backfill (`blocked`, `success`, `success`) | An empty range is never published (blocked by `volume_not_collapsed`); a real range loads and publishes its snapshots; repeating it loads 0 files and gives identical Gold. |
| `source_failure` | baseline → every API request returns HTTP 503 → source recovers after 2 transient 503s (`success`, `failed`, `success`) | A source outage fails the run without publishing partial data; recovery is automatic on the next run. |

## Verified results (2026-11-26)

* Synthetic demo instance (`start-demo.cmd`), via the web UI endpoints: all four demos **PASSED** with exactly the step
  statuses listed above; the scheduler ("enable + run now") produced a successful scheduled run.
* Real-data instance (2026-11-25, before publication): all four demos **PASSED**; the published Gold fingerprint of the
  main warehouse was unchanged afterwards.
* Automated: `tests/test_demo.py` (each demo passes and leaves the main warehouse untouched) and
  `tests/test_demo_data.py` (the failed-validation demo on freshly generated data).

## Bug found while preparing the public release

The `failed_validation` and `source_failure` demos injected records with fixed timestamps (`2026-11-25T…`). On a dataset whose
snapshots were newer than that date, the injected record was treated as an *older* version and ignored, so the demo
reported FAILED without blocking anything. The timestamps are now computed relative to the current time
(`_later()` in `skillradar/demo.py`), and a regression test covers it.
