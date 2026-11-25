-- SkillRadar warehouse schema (SQLite).
-- Layers are separated by table prefix:  bronze_*  silver_*  gold_*   plus ops_* (pipeline operations).
-- All statements are idempotent (IF NOT EXISTS) so init-db can be re-run safely.

PRAGMA foreign_keys = ON;

------------------------------------------------------------------------------
-- OPS: run history, task runs, data-quality results, alerts, API budget, watermarks
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops_pipeline_runs (
    run_id        TEXT PRIMARY KEY,
    run_type      TEXT NOT NULL,            -- pipeline | backfill | fetch
    trigger       TEXT NOT NULL,            -- cli | scheduler | test
    status        TEXT NOT NULL,            -- running | success | blocked | failed
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    duration_s    REAL,
    params_json   TEXT,
    error         TEXT
);

CREATE TABLE IF NOT EXISTS ops_task_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES ops_pipeline_runs(run_id) ON DELETE CASCADE,
    task_name     TEXT NOT NULL,
    status        TEXT NOT NULL,            -- success | failed | blocked | skipped
    attempts      INTEGER NOT NULL DEFAULT 0,
    started_at    TEXT,
    finished_at   TEXT,
    duration_s    REAL,
    rows_in       INTEGER,
    rows_out      INTEGER,
    details_json  TEXT,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS ix_task_runs_run ON ops_task_runs(run_id);

CREATE TABLE IF NOT EXISTS ops_dq_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES ops_pipeline_runs(run_id) ON DELETE CASCADE,
    check_name    TEXT NOT NULL,
    severity      TEXT NOT NULL,            -- blocking | warning
    passed        INTEGER NOT NULL,
    checked_count INTEGER NOT NULL,
    failed_count  INTEGER NOT NULL,
    sample_json   TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_dq_run ON ops_dq_results(run_id);

CREATE TABLE IF NOT EXISTS ops_alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT,
    level         TEXT NOT NULL,            -- warning | error
    message       TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    metric        TEXT NOT NULL,
    value         REAL,
    value_text    TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_metrics_run ON ops_metrics(run_id);

-- Every live HTTP request (never the API key) for budget tracking and audit.
CREATE TABLE IF NOT EXISTS ops_api_requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT,
    requested_at  TEXT NOT NULL,
    endpoint      TEXT NOT NULL,
    params_json   TEXT,
    status_code   INTEGER,
    duration_ms   REAL,
    records       INTEGER,
    quota_limit   INTEGER,
    quota_used    INTEGER,
    attempt       INTEGER NOT NULL DEFAULT 1,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS ix_api_requests_time ON ops_api_requests(requested_at);

-- Incremental-load watermark: newest source `ingested_at` seen (Softon `updated_after` param).
CREATE TABLE IF NOT EXISTS ops_watermarks (
    source        TEXT PRIMARY KEY,
    watermark     TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    run_id        TEXT,
    resume_cursor TEXT,                     -- next cursor of an unfinished incremental walk
    resume_params TEXT                      -- the exact params that cursor belongs to
);

-- Single-row lock so the scheduler and a manual run cannot overlap.
CREATE TABLE IF NOT EXISTS ops_lock (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    run_id        TEXT NOT NULL,
    acquired_at   TEXT NOT NULL
);

------------------------------------------------------------------------------
-- BRONZE: raw files registry + raw records (PII-anonymised copy of the payload)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze_raw_files (
    file_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,            -- softon | esco
    file_kind     TEXT NOT NULL,            -- local_export | api_snapshot | reference_csv
    path          TEXT NOT NULL,            -- relative to data dir
    sha256        TEXT NOT NULL UNIQUE,     -- content hash => idempotent registration
    size_bytes    INTEGER NOT NULL,
    snapshot_at   TEXT,                     -- when the data was observed (see docs/data_sources.md)
    registered_at TEXT NOT NULL,
    record_count  INTEGER,
    run_id        TEXT,
    request_json  TEXT                      -- request params for api snapshots (no secrets)
);

CREATE TABLE IF NOT EXISTS bronze_softon_jobs (
    bronze_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id            INTEGER NOT NULL REFERENCES bronze_raw_files(file_id),
    record_index       INTEGER NOT NULL,
    job_id             TEXT,                -- Softon id "<source>:<native id>" (may be NULL/invalid in bad data)
    source_ingested_at TEXT,
    payload_json       TEXT NOT NULL,       -- full record, contact fields removed, PII redacted in text
    payload_sha256     TEXT NOT NULL,
    pii_redactions     INTEGER NOT NULL DEFAULT 0,
    loaded_at          TEXT NOT NULL,
    UNIQUE (file_id, record_index)
);
CREATE INDEX IF NOT EXISTS ix_bronze_jobs_job ON bronze_softon_jobs(job_id);

CREATE TABLE IF NOT EXISTS bronze_esco_occupations (
    occupation_uri   TEXT PRIMARY KEY,
    code             TEXT,
    isco_group       TEXT,
    preferred_label  TEXT NOT NULL,
    alt_labels       TEXT,
    hidden_labels    TEXT,
    status           TEXT,
    modified_date    TEXT,
    description      TEXT,
    file_id          INTEGER NOT NULL REFERENCES bronze_raw_files(file_id)
);
CREATE INDEX IF NOT EXISTS ix_esco_occ_isco ON bronze_esco_occupations(isco_group);

CREATE TABLE IF NOT EXISTS bronze_esco_skills (
    skill_uri        TEXT PRIMARY KEY,
    skill_type       TEXT,
    reuse_level      TEXT,
    preferred_label  TEXT NOT NULL,
    alt_labels       TEXT,
    hidden_labels    TEXT,
    status           TEXT,
    modified_date    TEXT,
    description      TEXT,
    file_id          INTEGER NOT NULL REFERENCES bronze_raw_files(file_id)
);
CREATE INDEX IF NOT EXISTS ix_esco_skill_label ON bronze_esco_skills(preferred_label);

CREATE TABLE IF NOT EXISTS bronze_esco_occupation_skills (
    occupation_uri   TEXT NOT NULL REFERENCES bronze_esco_occupations(occupation_uri),
    skill_uri        TEXT NOT NULL REFERENCES bronze_esco_skills(skill_uri),
    relation_type    TEXT NOT NULL,         -- essential | optional
    skill_type       TEXT,
    file_id          INTEGER NOT NULL REFERENCES bronze_raw_files(file_id),
    PRIMARY KEY (occupation_uri, skill_uri)
);
CREATE INDEX IF NOT EXISTS ix_esco_rel_skill ON bronze_esco_occupation_skills(skill_uri);

------------------------------------------------------------------------------
-- SILVER: cleaned, normalised, deduplicated, anonymised
------------------------------------------------------------------------------
-- Searchable label dictionary (ESCO preferred/alt labels + curated AZ/RU aliases)
CREATE TABLE IF NOT EXISTS silver_skill_labels (
    label_norm   TEXT NOT NULL,
    skill_uri    TEXT NOT NULL REFERENCES bronze_esco_skills(skill_uri),
    label        TEXT NOT NULL,
    label_type   TEXT NOT NULL,             -- preferred | alt | alias
    lang         TEXT NOT NULL,             -- en | az | ru
    PRIMARY KEY (label_norm, skill_uri)
);

CREATE TABLE IF NOT EXISTS silver_vacancies (
    job_id               TEXT PRIMARY KEY,  -- Softon id "<source>:<native id>"
    source               TEXT NOT NULL,
    source_name          TEXT,
    native_id            TEXT,
    title                TEXT,
    title_norm           TEXT,
    company_name         TEXT,
    company_key          TEXT,
    location_raw         TEXT,
    city                 TEXT,
    district             TEXT,
    country              TEXT,
    remote               INTEGER,
    employment_type      TEXT,
    employment_type_raw  TEXT,
    job_function_raw     TEXT,
    career_level_raw     TEXT,
    salary_from          REAL,
    salary_to            REAL,
    salary_currency      TEXT,
    salary_period        TEXT,
    has_salary           INTEGER NOT NULL,
    posted_at            TEXT,
    posted_date          TEXT,
    deadline_at          TEXT,
    first_seen_at        TEXT,
    source_ingested_at   TEXT,
    active               INTEGER,
    url                  TEXT,
    description_text     TEXT,              -- PII redacted
    requirements_text    TEXT,              -- PII redacted
    has_text             INTEGER NOT NULL,
    text_lang            TEXT,              -- heuristic: az | ru | en | unknown
    has_contact_email    INTEGER NOT NULL DEFAULT 0,
    has_contact_phone    INTEGER NOT NULL DEFAULT 0,
    bronze_id            INTEGER NOT NULL REFERENCES bronze_softon_jobs(bronze_id),
    file_id              INTEGER NOT NULL REFERENCES bronze_raw_files(file_id),
    snapshot_at          TEXT,
    versions_seen        INTEGER NOT NULL,
    is_duplicate         INTEGER NOT NULL DEFAULT 0,
    canonical_job_id     TEXT,
    skill_status         TEXT,              -- matched | no_match | no_text
    built_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_silver_vac_source ON silver_vacancies(source);
CREATE INDEX IF NOT EXISTS ix_silver_vac_company ON silver_vacancies(company_key);
CREATE INDEX IF NOT EXISTS ix_silver_vac_posted ON silver_vacancies(posted_date);

CREATE TABLE IF NOT EXISTS silver_duplicate_links (
    job_id           TEXT PRIMARY KEY REFERENCES silver_vacancies(job_id) ON DELETE CASCADE,
    canonical_job_id TEXT NOT NULL REFERENCES silver_vacancies(job_id) ON DELETE CASCADE,
    rule             TEXT NOT NULL,
    evidence_json    TEXT
);

CREATE TABLE IF NOT EXISTS silver_normalization_issues (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT,
    field      TEXT NOT NULL,
    raw_value  TEXT,
    issue      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_job_skills (
    job_id       TEXT NOT NULL REFERENCES silver_vacancies(job_id) ON DELETE CASCADE,
    skill_uri    TEXT NOT NULL REFERENCES bronze_esco_skills(skill_uri),
    field        TEXT NOT NULL,             -- title | description | requirements
    start_pos    INTEGER NOT NULL,
    end_pos      INTEGER NOT NULL,
    matched_text TEXT NOT NULL,             -- exact text found in the posting
    label        TEXT NOT NULL,             -- dictionary label that matched
    label_type   TEXT NOT NULL,
    lang         TEXT NOT NULL,
    snippet      TEXT,
    PRIMARY KEY (job_id, skill_uri, field, start_pos)
);
CREATE INDEX IF NOT EXISTS ix_job_skills_skill ON silver_job_skills(skill_uri);

CREATE TABLE IF NOT EXISTS silver_job_occupations (
    job_id         TEXT PRIMARY KEY REFERENCES silver_vacancies(job_id) ON DELETE CASCADE,
    occupation_uri TEXT NOT NULL REFERENCES bronze_esco_occupations(occupation_uri),
    matched_text   TEXT NOT NULL,
    label          TEXT NOT NULL,
    label_type     TEXT NOT NULL,
    lang           TEXT NOT NULL
);

------------------------------------------------------------------------------
-- GOLD: published analytical tables (replaced atomically, only after DQ passes)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold_publications (
    version          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT NOT NULL,
    published_at     TEXT NOT NULL,
    vacancy_count    INTEGER NOT NULL,
    row_counts_json  TEXT NOT NULL,
    freshness_json   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gold_source_summary (
    source              TEXT PRIMARY KEY,
    source_name         TEXT,
    vacancies           INTEGER NOT NULL,   -- after cross-source dedup
    duplicates_removed  INTEGER NOT NULL,
    share_pct           REAL NOT NULL,
    with_salary         INTEGER NOT NULL,
    with_text           INTEGER NOT NULL,
    with_skills         INTEGER NOT NULL,
    first_posted_at     TEXT,
    last_posted_at      TEXT,
    last_source_ingested_at TEXT
);

CREATE TABLE IF NOT EXISTS gold_company_summary (
    company_key         TEXT PRIMARY KEY,
    company_name        TEXT NOT NULL,
    vacancies           INTEGER NOT NULL,
    sources             INTEGER NOT NULL,
    with_salary         INTEGER NOT NULL,
    median_salary_from  REAL,
    salary_currency     TEXT,
    last_posted_at      TEXT
);

CREATE TABLE IF NOT EXISTS gold_occupation_demand (
    occupation_uri   TEXT PRIMARY KEY,
    occupation_label TEXT NOT NULL,
    isco_group       TEXT,
    vacancies        INTEGER NOT NULL,
    example_titles   TEXT
);

CREATE TABLE IF NOT EXISTS gold_salary_coverage (
    scope             TEXT PRIMARY KEY,     -- ALL or a source
    vacancies         INTEGER NOT NULL,
    with_any_salary   INTEGER NOT NULL,
    with_full_range   INTEGER NOT NULL,
    coverage_pct      REAL NOT NULL,
    currency          TEXT,
    period_stated     INTEGER NOT NULL,
    min_salary_from   REAL,
    median_salary_from REAL,
    median_salary_to  REAL,
    max_salary_to     REAL
);

CREATE TABLE IF NOT EXISTS gold_skill_demand (
    skill_uri          TEXT PRIMARY KEY,
    skill_label        TEXT NOT NULL,
    skill_type         TEXT,
    vacancies          INTEGER NOT NULL,
    share_of_text_pct  REAL NOT NULL,       -- share of vacancies WITH text (unknown != absent)
    evidence_langs     TEXT,
    example_evidence   TEXT,
    example_job_id     TEXT
);

CREATE TABLE IF NOT EXISTS gold_publication_trend (
    date_basis   TEXT NOT NULL,             -- posted_date | first_seen_date
    day          TEXT NOT NULL,
    source       TEXT NOT NULL,             -- ALL or a source
    vacancies    INTEGER NOT NULL,
    PRIMARY KEY (date_basis, day, source)
);

------------------------------------------------------------------------------
-- GOLD (Phase 2): published, validated vacancy-level data for the website.
-- Written in the SAME transaction as the aggregates, only after the quality gate passes,
-- so the web app never reads Silver (which may hold a candidate that failed validation).
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold_vacancies (
    job_id            TEXT PRIMARY KEY,
    source            TEXT NOT NULL,
    source_name       TEXT,
    title             TEXT NOT NULL,
    company_name      TEXT,
    company_key       TEXT,
    city              TEXT NOT NULL,
    employment_type   TEXT,
    job_function_raw  TEXT,
    career_level_raw  TEXT,
    salary_from       REAL,
    salary_to         REAL,
    salary_currency   TEXT,
    salary_period     TEXT,
    has_salary        INTEGER NOT NULL,
    posted_at         TEXT,
    posted_date       TEXT,
    deadline_at       TEXT,
    first_seen_at     TEXT,
    url               TEXT,
    description_text  TEXT,                 -- PII-redacted
    requirements_text TEXT,                 -- PII-redacted
    has_text          INTEGER NOT NULL,
    text_lang         TEXT,
    skill_status      TEXT,
    skill_count       INTEGER NOT NULL,
    occupation_uri    TEXT,
    occupation_label  TEXT,
    occupation_match  TEXT,                 -- exact title text that matched the occupation
    also_listed_on    TEXT                  -- JSON [{job_id, source, url}] cross-source duplicates
);
CREATE INDEX IF NOT EXISTS ix_gold_vac_posted ON gold_vacancies(posted_at);
CREATE INDEX IF NOT EXISTS ix_gold_vac_occ ON gold_vacancies(occupation_uri);

CREATE TABLE IF NOT EXISTS gold_vacancy_skills (
    job_id       TEXT NOT NULL REFERENCES gold_vacancies(job_id) ON DELETE CASCADE,
    skill_uri    TEXT NOT NULL,
    skill_label  TEXT NOT NULL,
    skill_type   TEXT,
    field        TEXT NOT NULL,
    start_pos    INTEGER NOT NULL,
    end_pos      INTEGER NOT NULL,
    matched_text TEXT NOT NULL,
    label        TEXT NOT NULL,
    label_type   TEXT NOT NULL,
    lang         TEXT NOT NULL,
    snippet      TEXT,
    PRIMARY KEY (job_id, skill_uri, field, start_pos)
);
CREATE INDEX IF NOT EXISTS ix_gold_vs_skill ON gold_vacancy_skills(skill_uri);

------------------------------------------------------------------------------
-- OPS (Phase 2): web-triggered operations and scheduler state
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops_admin_operations (
    op_id        TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,             -- run | fetch_live | backfill | demo:<name>
    status       TEXT NOT NULL,             -- queued | running | success | blocked | failed
    params_json  TEXT,
    requested_at TEXT NOT NULL,
    started_at   TEXT,
    finished_at  TEXT,
    run_id       TEXT,
    result_json  TEXT,
    error        TEXT
);

CREATE TABLE IF NOT EXISTS ops_scheduler_state (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    enabled        INTEGER NOT NULL,
    mode           TEXT NOT NULL,           -- web | cli
    interval_hours REAL NOT NULL,
    live           INTEGER NOT NULL,
    started_at     TEXT,
    last_run_at    TEXT,
    last_run_id    TEXT,
    last_status    TEXT,
    next_run_at    TEXT,
    heartbeat_at   TEXT
);
