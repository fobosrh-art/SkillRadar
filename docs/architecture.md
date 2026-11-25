# Architecture

## Design goals
1. **Reproducible from raw files.** Raw inputs are never modified. Everything downstream can be rebuilt.
2. **Idempotent.** Running any step twice gives the same result (content-hash file registry, full deterministic
   Silver rebuild, atomic Gold replacement).
3. **Publish only validated data.** Blocking data-quality checks guard the Gold layer.
4. **Explainable.** Every extracted skill stores the exact text that matched and its character offsets.
5. **Simple to run on Windows.** One SQLite file, plain Python, no Docker.

## Code layout

```
skillradar/
  config.py               settings from env/.env (paths, API, budgets, retries)
  db.py, schema.sql       SQLite connection (WAL, foreign keys), schema for all layers
  ingestion/
    registry.py           raw-file registry (SHA-256 → idempotent)
    esco.py               ESCO CSV → bronze_esco_* (FK-checked, orphans counted)
    softon_local.py       local JSON / snapshots → bronze_softon_jobs (PII anonymised)
    softon_api.py         live client: cursor pagination, budget, retries/backoff, timeouts, watermark
  transform/
    text.py               offset-preserving folding (ə→e, İ→i …), tokeniser, language heuristic
    pii.py                contact-data removal and e-mail/phone redaction
    normalize.py          city, dates, currency, amounts, employment type, company key
    dedup.py              conservative cross-source duplicate detection
    silver.py             Bronze → silver_vacancies (latest version per id)
  skills/
    matcher.py            hash-map n-gram matcher + stem aliases + overlap resolution
    extractor.py          builds dictionaries, writes silver_job_skills / silver_job_occupations
    resources/*.csv       curated multilingual aliases → ESCO preferred labels
  quality/checks.py       blocking + warning checks, results to ops_dq_results
  gold/build.py           Gold tables, freshness, atomic publish, CSV export
  pipeline/runner.py      DAG, retries, run/task history, metrics, alerts, lock, backfill
  pipeline/scheduler.py   APScheduler interval job + recovery retry
  cli.py, __main__.py     command line
  api.py                  read-only FastAPI over Gold
```

## Layers

| Layer | Storage | Rule |
|---|---|---|
| Landing (raw) | `data/raw/**` files | Immutable. API pages are written with `open(path, "xb")`, so an existing snapshot can never be overwritten. |
| Bronze | `bronze_*` tables | One row per raw record per file, keyed by `(file_id, record_index)`. The payload is kept complete apart from PII anonymisation. Provenance: `file_id → bronze_raw_files(path, sha256, snapshot_at, request_json)`. |
| Silver | `silver_*` tables | Rebuilt fully from Bronze on every run. Takes the newest version per Softon id (snapshot time, then source `ingested_at`, then load order). Normalised, deduplicated, with evidence tables. |
| Gold | `gold_*` tables | Aggregates over **canonical** (non-duplicate) vacancies. Replaced inside one transaction, and only after the quality gate passes. `gold_publications` versions each publication. |
| Processed | `data/processed/gold/*.csv` | CSV export of the currently published Gold version. |
| Ops | `ops_*` tables | Run history, task runs, DQ results, alerts, metrics, API request log, watermarks, lock. |

All layers share one SQLite file, separated by table prefix. That keeps foreign keys (Silver → Bronze → raw file)
enforceable and lets one transaction cover a publication.

## Orchestration

```
ingest_esco ───────────────────────────────┐
fetch_live (only with --live) ──┐          │
                                ▼          ▼
                 ingest_raw → build_silver → extract_skills → quality_gate → publish_gold
```

* Tasks run in dependency order. If a dependency is not `success`, the task is recorded as `skipped`
  with the reason (`upstream_not_successful`).
* **Retries:** unexpected exceptions are retried `SKILLRADAR_TASK_RETRIES` times (default 1) with linear
  backoff. A quality-gate block is deterministic and is never retried. The HTTP client has its own retries
  (exponential backoff and `Retry-After`).
* **Recovery:** every task is idempotent, so recovery means running the pipeline again. The scheduler does this
  automatically once, `--retry-minutes` after a failed or blocked run.
* **Lock:** the single-row `ops_lock` table stops a scheduler run and a manual run from overlapping.
  A lock older than 2 h counts as stale and is removed.
* **History and metrics per run:** `ops_pipeline_runs` (status, duration, params, error) and
  `ops_task_runs` (attempts, duration, rows_out, JSON details). `ops_metrics` holds row counts of every
  bronze/silver/gold table, the published Gold version, freshness ages in hours and run duration.
* **Alerts:** each failure, block or DQ warning writes a row to `ops_alerts`, appends a line to
  `data/logs/alerts.log` and logs a console error.

## Backfill semantics
`backfill --start D1 --end D2` loads every raw Softon file whose **snapshot date** falls in [D1, D2] and is
not yet in Bronze, then rebuilds Silver and Gold. Silver is always rebuilt from all of Bronze, so the outcome is
the same whatever order snapshots arrive in, and repeating a backfill changes nothing.
Snapshot date: the live fetcher's sidecar `fetched_at` if present, otherwise the newest record
`ingested_at`, otherwise the file modification time. The basis used is stored in `bronze_raw_files.request_json`.

## Incremental live loading (no-skip design, revised in Phase 2)
* Watermark = `ops_watermarks.softon` (before the first live walk: newest `source_ingested_at` in Bronze).
* With a watermark the client requests `updated_after=<watermark>&order=ingested_at` (ascending, keyset cursor).
* Softon ingests in batches: in the real live page 99 of 100 rows share one `ingested_at`. `updated_after` is
  *strictly later*, so the Phase-1 rule "watermark = last timestamp of the page" would have skipped the rest of that
  batch on the next run. Now:
  * while a walk is unfinished, the next cursor **and the exact parameters it belongs to** are stored
    (`resume_cursor`, `resume_params`), and the next run continues that walk;
  * the watermark only advances to the newest timestamp that is strictly older than the page's last timestamp
    (that batch is provably complete); when the walk reaches the last page it becomes the newest timestamp seen;
  * a rejected cursor (HTTP 400) is discarded and the walk restarts from the tie-safe watermark. Re-fetched rows
    are harmless because Bronze stores versions and Silver keeps the newest.
  * Each page is persisted to Bronze before the state moves, so a crash cannot lose records.
  * `python -m skillradar repair-watermark` recomputed the stored state from the saved snapshots (no network).
* Without one (or with `--full`) it walks newest-first. In that case the watermark is set only if the walk reached the last page.
* Budget: each 2xx response is logged in `ops_api_requests`. Remaining budget = min(local monthly budget − used,
  `X-Quota-Limit − X-Quota-Used` from the last response). A request is refused when the remaining budget is 0.
  `429 quota_exceeded` is never retried. `429 rate_limited` and 5xx/timeouts are retried.


## Web layer (Phase 2)
* `skillradar/web/app.py`: FastAPI JSON API under `/api` + the built React app (`frontend/dist`) with an SPA fallback.
  Vacancy data is read only from `gold_*` tables. `gold_vacancies` and `gold_vacancy_skills` are written in the same
  transaction as the aggregates, after the quality gate, so a blocked run never exposes candidate Silver rows.
* `skillradar/web/career.py`: Career Match (market vs ESCO evidence kept separate, exact-URI matching) and the
  Roadmap score (50 × occupation market share + 30 × ESCO weight + 20 × normalised Baku demand).
* `skillradar/web/admin.py`: background operations (`ops_admin_operations`), localhost + anti-CSRF guard,
  a process lock shared with the in-app scheduler, plus the database `ops_lock` → HTTP 409 on overlap.
* `skillradar/pipeline/scheduler.py`: `WebScheduler` (BackgroundScheduler, local pipeline only) and the CLI
  BlockingScheduler; both write `ops_scheduler_state` (heartbeat, next run, last status).
* `skillradar/demo.py`: sandbox demonstrations (see docs/reliability_demonstrations.md).
* Per-request SQLite connections (WAL mode allows reads during a pipeline write). `check_same_thread=False` because
  FastAPI may create the dependency and run the endpoint on different threadpool threads; a connection is never shared
  between requests.


## Phase 3 additions

### Frontend robustness
* **Navigation bug (root cause):** an expression-bodied effect, `useEffect(() => window.scrollTo(0, 0), …)`, returned the
  Promise that current Chrome's `scrollTo()` yields. React treats an effect's return value as its cleanup and called it
  on the next route change (`TypeError: destroy is not a function`). Without an error boundary React unmounted the whole
  tree, leaving a blank page until a manual reload. Fixed with a block-bodied effect.
* A per-route **error boundary** (`ErrorBoundary`, keyed by pathname) now contains any page render error; the sidebar keeps working
  and leaving the page clears the error.
* Static regression test `tests/test_frontend_static.py` rejects expression-bodied effects.

### Localisation
* `react-i18next` with three resource files (`frontend/src/i18n/{ru,az,en}.ts`). RU and AZ are typed against EN, so
  a missing key fails `tsc`. Default language: Russian; the choice is stored in `localStorage['skillradar.lang']`, and
  `<html lang>` is updated.
* All formatting goes through `lib/format.ts`: `Intl` number/percent/date formatting in the active locale
  (`ru-RU`, `az-Latn-AZ`, `en-GB`) and **`Asia/Baku`** as the display timezone. Calendar days (YYYY-MM-DD) are formatted
  without a timezone shift.
* Server-side prose was removed from the UI path: the frontend renders explanations, rules, demo steps and roadmap
  reasons from structured fields (check names, step indices + parameters, counts), so every language is complete.
  Stored operational messages (alerts) remain in English and are labelled as such.

### Scheduled local processing vs scheduled live ingestion
| | In-app scheduler (Operations page) | CLI `schedule` | CLI `schedule --live` |
|---|---|---|---|
| What it runs | local pipeline over raw files already on disk | same | live Softon fetch + pipeline |
| API cost | none | none | 1 request per page per run |
| Status | verified (scheduled run recorded, 409 during it) | verified (Phase 1) | implemented, **not enabled**; needs explicit approval |

### Optional Docker (unverified)
`Dockerfile` (Node build stage + Python runtime) and `docker-compose.yml` (port published on 127.0.0.1 only, `./data`
mounted, `.env` as env_file). Requests reach a container from the bridge gateway, so admin access there requires listing it in
`SKILLRADAR_ADMIN_TRUSTED_HOSTS`; natively this variable is empty and only loopback is trusted.

### API client safeguards added before the approved live batch
* 1 s politeness delay between pages (free plan: 5 req/s).
* Quota reserve (`SOFTON_QUOTA_RESERVE`, default 5): the walk stops before using the last 5 requests of the
  month, based on min(local budget, `X-Quota-Limit − X-Quota-Used` from the latest response).


## Final release additions (2026-11-25)
* **Local ESCO label translations.** `skills/resources/label_translations.psv` (English ESCO preferred label → RU → AZ),
  resolved to URIs by `web/labels.py`; exposed at `GET /api/labels` with honest coverage figures. The frontend hook
  `lib/labels.ts` (`useEscoLabels`) picks the label for the active language instantly and falls back to English; the
  original ESCO label stays in tooltips. ESCO search endpoints also match RU/AZ labels. Classifier, URIs, matching
  and analytics are unchanged.
* **Job Explorer filters** (`GET /api/vacancies`): text, occupation, skill, employer, source, employment type,
  publication date (today / 3 / 7 / 30 days, Baku time), salary min/max with **overlap semantics** (one published
  bound = that value; no salary never matches), pay period (monthly / not stated), salary-only, sort by date or salary
  both ways. Applied in SQL to the whole Gold set; `min > max` → HTTP 400 (UI warns and does not apply it).
* **Skill counter fix.** `GET /api/skills` returns `total_skills` / `total_matches` computed with `COUNT(DISTINCT …)`;
  the former UI used the length of a list capped at 200 rows.
