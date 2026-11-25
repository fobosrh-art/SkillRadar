# Database schema (generated from the live SQLite warehouse)

Generated with `PRAGMA table_info` from `data/warehouse/skillradar.db` on 2026-11-25 (Gold v21); DDL source: `skillradar/schema.sql`.

Local RU/AZ display labels for ESCO concepts are **not** stored in the database: they live in `skillradar/skills/resources/label_translations.psv`, separate from the ESCO classifier.

## Bronze — raw records (PII-anonymised) and ESCO reference data

### `bronze_esco_occupation_skills` — 128,987 rows

| Column | Type | Key / reference |
|---|---|---|
| occupation_uri | TEXT | PK → bronze_esco_occupations.occupation_uri |
| skill_uri | TEXT | PK → bronze_esco_skills.skill_uri |
| relation_type | TEXT | NOT NULL |
| skill_type | TEXT |  |
| file_id | INTEGER | → bronze_raw_files.file_id NOT NULL |

Indexes: `ix_esco_rel_skill`

### `bronze_esco_occupations` — 3,039 rows

| Column | Type | Key / reference |
|---|---|---|
| occupation_uri | TEXT | PK |
| code | TEXT |  |
| isco_group | TEXT |  |
| preferred_label | TEXT | NOT NULL |
| alt_labels | TEXT |  |
| hidden_labels | TEXT |  |
| status | TEXT |  |
| modified_date | TEXT |  |
| description | TEXT |  |
| file_id | INTEGER | → bronze_raw_files.file_id NOT NULL |

Indexes: `ix_esco_occ_isco`

### `bronze_esco_skills` — 13,939 rows

| Column | Type | Key / reference |
|---|---|---|
| skill_uri | TEXT | PK |
| skill_type | TEXT |  |
| reuse_level | TEXT |  |
| preferred_label | TEXT | NOT NULL |
| alt_labels | TEXT |  |
| hidden_labels | TEXT |  |
| status | TEXT |  |
| modified_date | TEXT |  |
| description | TEXT |  |
| file_id | INTEGER | → bronze_raw_files.file_id NOT NULL |

Indexes: `ix_esco_skill_label`

### `bronze_raw_files` — 21 rows

| Column | Type | Key / reference |
|---|---|---|
| file_id | INTEGER | PK |
| source | TEXT | NOT NULL |
| file_kind | TEXT | NOT NULL |
| path | TEXT | NOT NULL |
| sha256 | TEXT | NOT NULL |
| size_bytes | INTEGER | NOT NULL |
| snapshot_at | TEXT |  |
| registered_at | TEXT | NOT NULL |
| record_count | INTEGER |  |
| run_id | TEXT |  |
| request_json | TEXT |  |

### `bronze_softon_jobs` — 1,621 rows

| Column | Type | Key / reference |
|---|---|---|
| bronze_id | INTEGER | PK |
| file_id | INTEGER | → bronze_raw_files.file_id NOT NULL |
| record_index | INTEGER | NOT NULL |
| job_id | TEXT |  |
| source_ingested_at | TEXT |  |
| payload_json | TEXT | NOT NULL |
| payload_sha256 | TEXT | NOT NULL |
| pii_redactions | INTEGER | NOT NULL |
| loaded_at | TEXT | NOT NULL |

Indexes: `ix_bronze_jobs_job`

## Silver — cleaned, normalised, deduplicated, with skill evidence

### `silver_duplicate_links` — 314 rows

| Column | Type | Key / reference |
|---|---|---|
| job_id | TEXT | PK → silver_vacancies.job_id |
| canonical_job_id | TEXT | → silver_vacancies.job_id NOT NULL |
| rule | TEXT | NOT NULL |
| evidence_json | TEXT |  |

### `silver_job_occupations` — 492 rows

| Column | Type | Key / reference |
|---|---|---|
| job_id | TEXT | PK → silver_vacancies.job_id |
| occupation_uri | TEXT | → bronze_esco_occupations.occupation_uri NOT NULL |
| matched_text | TEXT | NOT NULL |
| label | TEXT | NOT NULL |
| label_type | TEXT | NOT NULL |
| lang | TEXT | NOT NULL |

### `silver_job_skills` — 8,024 rows

| Column | Type | Key / reference |
|---|---|---|
| job_id | TEXT | PK → silver_vacancies.job_id |
| skill_uri | TEXT | PK → bronze_esco_skills.skill_uri |
| field | TEXT | PK |
| start_pos | INTEGER | PK |
| end_pos | INTEGER | NOT NULL |
| matched_text | TEXT | NOT NULL |
| label | TEXT | NOT NULL |
| label_type | TEXT | NOT NULL |
| lang | TEXT | NOT NULL |
| snippet | TEXT |  |

Indexes: `ix_job_skills_skill`

### `silver_normalization_issues` — 10 rows

| Column | Type | Key / reference |
|---|---|---|
| id | INTEGER | PK |
| job_id | TEXT |  |
| field | TEXT | NOT NULL |
| raw_value | TEXT |  |
| issue | TEXT | NOT NULL |

### `silver_skill_labels` — 88,575 rows

| Column | Type | Key / reference |
|---|---|---|
| label_norm | TEXT | PK |
| skill_uri | TEXT | PK → bronze_esco_skills.skill_uri |
| label | TEXT | NOT NULL |
| label_type | TEXT | NOT NULL |
| lang | TEXT | NOT NULL |

### `silver_vacancies` — 1,515 rows

| Column | Type | Key / reference |
|---|---|---|
| job_id | TEXT | PK |
| source | TEXT | NOT NULL |
| source_name | TEXT |  |
| native_id | TEXT |  |
| title | TEXT |  |
| title_norm | TEXT |  |
| company_name | TEXT |  |
| company_key | TEXT |  |
| location_raw | TEXT |  |
| city | TEXT |  |
| district | TEXT |  |
| country | TEXT |  |
| remote | INTEGER |  |
| employment_type | TEXT |  |
| employment_type_raw | TEXT |  |
| job_function_raw | TEXT |  |
| career_level_raw | TEXT |  |
| salary_from | REAL |  |
| salary_to | REAL |  |
| salary_currency | TEXT |  |
| salary_period | TEXT |  |
| has_salary | INTEGER | NOT NULL |
| posted_at | TEXT |  |
| posted_date | TEXT |  |
| deadline_at | TEXT |  |
| first_seen_at | TEXT |  |
| source_ingested_at | TEXT |  |
| active | INTEGER |  |
| url | TEXT |  |
| description_text | TEXT |  |
| requirements_text | TEXT |  |
| has_text | INTEGER | NOT NULL |
| text_lang | TEXT |  |
| has_contact_email | INTEGER | NOT NULL |
| has_contact_phone | INTEGER | NOT NULL |
| bronze_id | INTEGER | → bronze_softon_jobs.bronze_id NOT NULL |
| file_id | INTEGER | → bronze_raw_files.file_id NOT NULL |
| snapshot_at | TEXT |  |
| versions_seen | INTEGER | NOT NULL |
| is_duplicate | INTEGER | NOT NULL |
| canonical_job_id | TEXT |  |
| skill_status | TEXT |  |
| built_at | TEXT | NOT NULL |

Indexes: `ix_silver_vac_posted`, `ix_silver_vac_company`, `ix_silver_vac_source`

## Gold — published, validated data served to the website

### `gold_company_summary` — 667 rows

| Column | Type | Key / reference |
|---|---|---|
| company_key | TEXT | PK |
| company_name | TEXT | NOT NULL |
| vacancies | INTEGER | NOT NULL |
| sources | INTEGER | NOT NULL |
| with_salary | INTEGER | NOT NULL |
| median_salary_from | REAL |  |
| salary_currency | TEXT |  |
| last_posted_at | TEXT |  |

### `gold_occupation_demand` — 80 rows

| Column | Type | Key / reference |
|---|---|---|
| occupation_uri | TEXT | PK |
| occupation_label | TEXT | NOT NULL |
| isco_group | TEXT |  |
| vacancies | INTEGER | NOT NULL |
| example_titles | TEXT |  |

### `gold_publication_trend` — 495 rows

| Column | Type | Key / reference |
|---|---|---|
| date_basis | TEXT | PK |
| day | TEXT | PK |
| source | TEXT | PK |
| vacancies | INTEGER | NOT NULL |

### `gold_publications` — 21 rows

| Column | Type | Key / reference |
|---|---|---|
| version | INTEGER | PK |
| run_id | TEXT | NOT NULL |
| published_at | TEXT | NOT NULL |
| vacancy_count | INTEGER | NOT NULL |
| row_counts_json | TEXT | NOT NULL |
| freshness_json | TEXT | NOT NULL |

### `gold_salary_coverage` — 29 rows

| Column | Type | Key / reference |
|---|---|---|
| scope | TEXT | PK |
| vacancies | INTEGER | NOT NULL |
| with_any_salary | INTEGER | NOT NULL |
| with_full_range | INTEGER | NOT NULL |
| coverage_pct | REAL | NOT NULL |
| currency | TEXT |  |
| period_stated | INTEGER | NOT NULL |
| min_salary_from | REAL |  |
| median_salary_from | REAL |  |
| median_salary_to | REAL |  |
| max_salary_to | REAL |  |

### `gold_skill_demand` — 340 rows

| Column | Type | Key / reference |
|---|---|---|
| skill_uri | TEXT | PK |
| skill_label | TEXT | NOT NULL |
| skill_type | TEXT |  |
| vacancies | INTEGER | NOT NULL |
| share_of_text_pct | REAL | NOT NULL |
| evidence_langs | TEXT |  |
| example_evidence | TEXT |  |
| example_job_id | TEXT |  |

### `gold_source_summary` — 29 rows

| Column | Type | Key / reference |
|---|---|---|
| source | TEXT | PK |
| source_name | TEXT |  |
| vacancies | INTEGER | NOT NULL |
| duplicates_removed | INTEGER | NOT NULL |
| share_pct | REAL | NOT NULL |
| with_salary | INTEGER | NOT NULL |
| with_text | INTEGER | NOT NULL |
| with_skills | INTEGER | NOT NULL |
| first_posted_at | TEXT |  |
| last_posted_at | TEXT |  |
| last_source_ingested_at | TEXT |  |

### `gold_vacancies` — 1,201 rows

| Column | Type | Key / reference |
|---|---|---|
| job_id | TEXT | PK |
| source | TEXT | NOT NULL |
| source_name | TEXT |  |
| title | TEXT | NOT NULL |
| company_name | TEXT |  |
| company_key | TEXT |  |
| city | TEXT | NOT NULL |
| employment_type | TEXT |  |
| job_function_raw | TEXT |  |
| career_level_raw | TEXT |  |
| salary_from | REAL |  |
| salary_to | REAL |  |
| salary_currency | TEXT |  |
| salary_period | TEXT |  |
| has_salary | INTEGER | NOT NULL |
| posted_at | TEXT |  |
| posted_date | TEXT |  |
| deadline_at | TEXT |  |
| first_seen_at | TEXT |  |
| url | TEXT |  |
| description_text | TEXT |  |
| requirements_text | TEXT |  |
| has_text | INTEGER | NOT NULL |
| text_lang | TEXT |  |
| skill_status | TEXT |  |
| skill_count | INTEGER | NOT NULL |
| occupation_uri | TEXT |  |
| occupation_label | TEXT |  |
| occupation_match | TEXT |  |
| also_listed_on | TEXT |  |

Indexes: `ix_gold_vac_occ`, `ix_gold_vac_posted`

### `gold_vacancy_skills` — 6,422 rows

| Column | Type | Key / reference |
|---|---|---|
| job_id | TEXT | PK → gold_vacancies.job_id |
| skill_uri | TEXT | PK |
| skill_label | TEXT | NOT NULL |
| skill_type | TEXT |  |
| field | TEXT | PK |
| start_pos | INTEGER | PK |
| end_pos | INTEGER | NOT NULL |
| matched_text | TEXT | NOT NULL |
| label | TEXT | NOT NULL |
| label_type | TEXT | NOT NULL |
| lang | TEXT | NOT NULL |
| snippet | TEXT |  |

Indexes: `ix_gold_vs_skill`

## Ops — run history, quality results, alerts, metrics, API log, state

### `ops_admin_operations` — 16 rows

| Column | Type | Key / reference |
|---|---|---|
| op_id | TEXT | PK |
| kind | TEXT | NOT NULL |
| status | TEXT | NOT NULL |
| params_json | TEXT |  |
| requested_at | TEXT | NOT NULL |
| started_at | TEXT |  |
| finished_at | TEXT |  |
| run_id | TEXT |  |
| result_json | TEXT |  |
| error | TEXT |  |

### `ops_alerts` — 2 rows

| Column | Type | Key / reference |
|---|---|---|
| id | INTEGER | PK |
| run_id | TEXT |  |
| level | TEXT | NOT NULL |
| message | TEXT | NOT NULL |
| created_at | TEXT | NOT NULL |

### `ops_api_requests` — 17 rows

| Column | Type | Key / reference |
|---|---|---|
| id | INTEGER | PK |
| run_id | TEXT |  |
| requested_at | TEXT | NOT NULL |
| endpoint | TEXT | NOT NULL |
| params_json | TEXT |  |
| status_code | INTEGER |  |
| duration_ms | REAL |  |
| records | INTEGER |  |
| quota_limit | INTEGER |  |
| quota_used | INTEGER |  |
| attempt | INTEGER | NOT NULL |
| error | TEXT |  |

Indexes: `ix_api_requests_time`

### `ops_dq_results` — 184 rows

| Column | Type | Key / reference |
|---|---|---|
| id | INTEGER | PK |
| run_id | TEXT | → ops_pipeline_runs.run_id NOT NULL |
| check_name | TEXT | NOT NULL |
| severity | TEXT | NOT NULL |
| passed | INTEGER | NOT NULL |
| checked_count | INTEGER | NOT NULL |
| failed_count | INTEGER | NOT NULL |
| sample_json | TEXT |  |
| created_at | TEXT | NOT NULL |

Indexes: `ix_dq_run`

### `ops_lock` — 0 rows

| Column | Type | Key / reference |
|---|---|---|
| id | INTEGER | PK |
| run_id | TEXT | NOT NULL |
| acquired_at | TEXT | NOT NULL |

### `ops_metrics` — 565 rows

| Column | Type | Key / reference |
|---|---|---|
| id | INTEGER | PK |
| run_id | TEXT | NOT NULL |
| metric | TEXT | NOT NULL |
| value | REAL |  |
| value_text | TEXT |  |
| created_at | TEXT | NOT NULL |

Indexes: `ix_metrics_run`

### `ops_pipeline_runs` — 23 rows

| Column | Type | Key / reference |
|---|---|---|
| run_id | TEXT | PK |
| run_type | TEXT | NOT NULL |
| trigger | TEXT | NOT NULL |
| status | TEXT | NOT NULL |
| started_at | TEXT | NOT NULL |
| finished_at | TEXT |  |
| duration_s | REAL |  |
| params_json | TEXT |  |
| error | TEXT |  |

### `ops_scheduler_state` — 1 rows

| Column | Type | Key / reference |
|---|---|---|
| id | INTEGER | PK |
| enabled | INTEGER | NOT NULL |
| mode | TEXT | NOT NULL |
| interval_hours | REAL | NOT NULL |
| live | INTEGER | NOT NULL |
| started_at | TEXT |  |
| last_run_at | TEXT |  |
| last_run_id | TEXT |  |
| last_status | TEXT |  |
| next_run_at | TEXT |  |
| heartbeat_at | TEXT |  |

### `ops_task_runs` — 140 rows

| Column | Type | Key / reference |
|---|---|---|
| id | INTEGER | PK |
| run_id | TEXT | → ops_pipeline_runs.run_id NOT NULL |
| task_name | TEXT | NOT NULL |
| status | TEXT | NOT NULL |
| attempts | INTEGER | NOT NULL |
| started_at | TEXT |  |
| finished_at | TEXT |  |
| duration_s | REAL |  |
| rows_in | INTEGER |  |
| rows_out | INTEGER |  |
| details_json | TEXT |  |
| error | TEXT |  |

Indexes: `ix_task_runs_run`

### `ops_watermarks` — 1 rows

| Column | Type | Key / reference |
|---|---|---|
| source | TEXT | PK |
| watermark | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |
| run_id | TEXT |  |
| resume_cursor | TEXT |  |
| resume_params | TEXT |  |
