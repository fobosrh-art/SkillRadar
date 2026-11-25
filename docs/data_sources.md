# Data sources, provenance and schemas

## 1. Softon Job Data API
* Endpoint: `GET https://api.softon.dev/v1/jobs`, bearer token from `SOFTON_API_KEY`.
* Contract verified from the official machine-readable schema `https://api.softon.dev/v1/schema`
  (public Softon API schema, read on 2026-11-25 without authentication; not redistributed here):
  * envelope `{data, meta, error}`; `meta.next` = opaque cursor, `null` on the last page
  * `limit` 1–100 (default 25), `cursor`, `order` (`ingested_at`, `posted_at`, `-` prefix = descending)
  * `city` (exact match on the normalised city), `include=bodies` (adds `description_html`, `requirements_html`)
  * `updated_after` (rows whose `ingested_at` is later; the documented way to tail changes)
  * errors: 400, 401 `missing_authorization`/`unauthorized`, 403, 404, 410, 429 `rate_limited` (retry),
    429 `quota_exceeded` (do not retry); headers `X-Quota-Limit`, `X-Quota-Used`, `Retry-After`
  * plans: free = 100 requests/month (our default `SOFTON_MONTHLY_BUDGET`)
* The provided export `data/raw/softon/jobs_baku.json` was produced with `city=Bakı, limit=100, include=bodies`.
  It is UTF-8 **with BOM** (PowerShell output), so it is read with `utf-8-sig`.

### Observed export profile (100 records)
| Field | Non-null | Notes |
|---|---|---|
| id | 100 | `<source>:<native id>`; some native ids have 9+ digits (`hh1_az:139796960`) |
| source | 100 | 10 sources: boss_az 41, smartjob_az 19, glorri 13, jooble_az 7, holo_az 6, work_az 4, hh1_az 4, hrin_co 4, energyjobsearch 1, tecrube_az 1 |
| location / city | 100 / 100 | `Bakı` 82, `Bakı, Azərbaycan` 13, `Баку` 4, `Baku, Azerbaijan` 1; `city` always `Bakı` |
| company | 97 | object `{name, slug}` |
| salary_from / salary_to | 49 / 49 | AZN only; 2 postings have only a floor, 2 only a ceiling |
| salary_period | 8 | `MONTH` |
| employment_type | 66 | mixed vocabularies: `Full-time`, `FULL_TIME`, `CONTRACTOR`, `Internship` … |
| career_level | 16 | includes the placeholder `career-levels.undefined` (→ null) |
| posted_at | 100 | all on 2026-11-24 |
| description / requirements | 76 / 45 | 70 % Azerbaijani, 11 % Russian, rest English/unknown (heuristic) |
| contact_email / contact_phone | 18 / 14 | **personal data**, removed at ingestion |

## 2. ESCO v1.2.0 (European Skills, Competences, Qualifications and Occupations)
Source: European Commission, CSV export, English. Licence: ESCO is free to reuse
(see the ESCO portal terms of use). Files and what was loaded:

| File | Rows loaded | Key columns used |
|---|---|---|
| occupations_en.csv | 3,039 | conceptUri, code, iscoGroup, preferredLabel, altLabels, hiddenLabels, status, description |
| skills_en.csv | 13,939 (10,715 skill/competence, 3,219 knowledge, 5 untyped) | conceptUri, skillType, reuseLevel, preferredLabel, altLabels |
| occupationSkillRelations_en.csv | 128,987 (0 orphans) | occupationUri, relationType (essential/optional), skillType, skillUri |

Multi-line `altLabels` cells are split on newlines.

## 3. Provenance chain
Every Gold number traces back through these keys:
`gold_* ← silver_vacancies.job_id → bronze_id → bronze_softon_jobs.file_id → bronze_raw_files(path, sha256, snapshot_at)`.
Skill evidence: `silver_job_skills(job_id, skill_uri, field, start_pos, end_pos, matched_text, label, label_type, lang, snippet)`.
Cross-source duplicates: `silver_duplicate_links(job_id, canonical_job_id, rule, evidence_json)`. Duplicates are flagged, never deleted.

## 4. Main table schemas (abridged; full DDL in `skillradar/schema.sql`)

**silver_vacancies** (PK `job_id`): source, native_id, title, title_norm, company_name, company_key,
location_raw, city, district, country, remote, employment_type (normalised), employment_type_raw,
job_function_raw, career_level_raw, salary_from, salary_to, salary_currency, salary_period, has_salary,
posted_at, posted_date, deadline_at, first_seen_at, source_ingested_at, active, url, description_text*,
requirements_text*, has_text, text_lang, has_contact_email, has_contact_phone, bronze_id (FK), file_id (FK),
snapshot_at, versions_seen, is_duplicate, canonical_job_id, skill_status (`matched|no_match|no_text`).
(* PII-redacted)

**gold_skill_demand**: skill_uri, skill_label, skill_type, vacancies, share_of_text_pct, evidence_langs,
example_evidence, example_job_id.
**gold_salary_coverage**: scope (ALL / source), vacancies, with_any_salary, with_full_range, coverage_pct, currency,
period_stated, min/median salary_from, median/max salary_to.
**gold_source_summary**, **gold_company_summary**, **gold_occupation_demand**, **gold_publication_trend**
(`date_basis` = `posted_date` or `first_seen_date`), **gold_publications** (version, run_id, vacancy_count,
row_counts_json, freshness_json).

## 5. Normalisation rules (no fabrication)
| Field | Rule |
|---|---|
| id | `<lower-case source>:<native id stripped>`; malformed ids → `__invalid__:bronzeN`, which fails the DQ gate |
| city | `Bakı / Baku / Баку` (any case or diacritics), with optional country part → `Baku`; anything else kept as-is and blocks the gate |
| dates | parsed ISO-8601 → UTC `YYYY-MM-DDTHH:MM:SSZ`; unparsable values kept raw and logged |
| salary | numbers or numeric strings > 0; `0`, negative or text → *not stated* (null). Never imputed. The currency is dropped if no amount is present |
| currency | `azn`, `manat`, `₼` → `AZN`; unknown codes kept upper-case and logged |
| employment_type | `Full-time`/`FULL_TIME` → `full_time`, `CONTRACTOR` → `contract` …; unmapped → `other` (raw kept); null stays null |
| career_level, job_function | kept as source labels (not comparable across sources); placeholders → null |
| company | display name kept; `company_key` = folded name without legal forms (MMC, ASC, QSC, LLC …). No company → not attributed |

## 6. Personal data
At Bronze ingestion (`transform/pii.py`):
* `contact_email`, `contact_phone` (including `facts.contact_email`) are removed and replaced by `*_present` flags.
* E-mails and phone-like digit runs (9–13 digits) in every text field are replaced by `[EMAIL]` / `[PHONE]`.
  Identifier and URL fields are excluded so native ids stay intact.
* Verified on the real data: none of the 18 source e-mails or 13 phone numbers appear anywhere in the database dump.
  The blocking check `no_contact_pii_in_text` re-verifies this on every run.
* The API exposes Gold only, so no posting text and no contact flags are served.
* Raw files on disk still contain the original data. They are git-ignored and must stay private.


## Collected data in Phase 3 (2026-11-25; later grew to 1,621 raw records, see final-results.md)
| File | Kind | Records |
|---|---|---|
| `raw/softon/jobs_baku.json` | provided export (first page of `-posted_at`) | 100 |
| `raw/softon/snapshots/2026/11/24/…221805…_p001.json` | live, incremental walk page 1 (student, Phase 2) | 100 |
| `raw/softon/snapshots/2026/11/24/…231352…_p001.json` | live, resumed walk (approved batch) | 100 |
| `…231353…_p002.json` | live | 100 |
| `…231355…_p003.json` | live, last page (`meta.next = null`) | 21 |

421 raw records → 402 published vacancies (19 cross-source duplicates). Sources in Bronze: 15 (Vakansiya.biz,
Xsolla, Vakansiya.az, Boss.az, Smartjob, Yapı Kredi, Glorri, jooble.az, hh1.az, HRIN, work.az, Energy JobSearch, Holo, Ziraat,
Tecrube.az). Note the observed profile above (section 1) describes the original 100-record export only.


## 7. Licensing and redistribution (checked 2026-11-26)

| Data | Terms found | Decision for the public repository |
|---|---|---|
| Softon job postings | The acceptable-use page (softon.dev/docs/shared/use, "plain language, not a contract") allows building products on the data and caching it, asks users not to resell the data or republish the corpus in bulk without asking first, requires the original `url` to stay reachable when a posting is shown to a person, and requires deleting removed records. | Raw exports, API snapshots and the SQLite warehouse with real vacancies are **not published**. The application keeps the original posting link on every vacancy. |
| Softon API schema | Public documentation; no explicit redistribution licence found. | Not copied into the public repository; see the Softon documentation. |
| ESCO v1.2.0 | Free download from the ESCO portal. The European Commission's reuse policy (Decision 2011/833/EU) and the Commission legal notice (CC BY 4.0 for Commission-owned content, credit and indication of changes required) apply to Commission content; the ESCO pages checked do not state a licence explicitly. | ESCO CSV files are **not redistributed**; users download them from the portal. The project's own RU/AZ display labels for ESCO concepts are marked as unofficial translations. Source credit: *ESCO, European Commission*. |
| Synthetic demo data | Generated by `skillradar/demo_data.py`. | Not stored in the repository; generated locally by `start-demo.cmd`. |

## 8. Synthetic demo dataset

`start-demo.cmd` sets `SKILLRADAR_DEMO=1` and `SKILLRADAR_DATA_DIR=data-demo`, generates about 430 fictional
vacancies (5 fictional job boards, about 50 fictional employers, URLs on `example.com`, salaries in AZN) and a small
synthetic taxonomy in the ESCO CSV layout (73 skills, 15 occupations, URIs on `example.org`), then runs the normal
pipeline. It never reads `data/` and never calls the live API (the API key is ignored in demo mode). Every page shows
a "Synthetic demo data" banner. About 5 % of the records are cross-board mirrors so that deduplication can be seen.
