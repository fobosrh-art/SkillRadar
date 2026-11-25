# Data-quality gate

Runs as the `quality_gate` task after Silver and skill extraction, before Gold. Results are stored per run in
`ops_dq_results` (check, severity, checked, failed, sample).

| # | Check | Severity | Rule |
|---|---|---|---|
| 1 | `unique_normalized_ids` | blocking | id matches `<source>:<native>`, the prefix equals `source`, `(source, native_id)` is unique, no `__invalid__` ids |
| 2 | `non_empty_titles` | blocking | title not null and not blank |
| 3 | `valid_dates` | blocking | a **present** `posted_at` must be parseable, ≥ 2000-01-01, ≤ now + 1 day; a **missing** `posted_at` is kept missing and counted (not guessed); `deadline_at` parseable when present |
| 4 | `valid_salary_ranges` | blocking | only rows that state a salary: 0 < amount ≤ 1,000,000, `from ≤ to`, known currency |
| 5 | `normalized_baku_location` | blocking | every vacancy normalises to `city = 'Baku'` |
| 6 | `no_contact_pii_in_text` | blocking | no e-mail or phone pattern left in title, description, requirements or company |
| 7 | `volume_not_collapsed` | blocking | canonical vacancies > 0 and ≥ 50 % of the last publication (catches partial loads) |
| 8 | `salary_coverage_info` | warning | alerts if < 10 % of vacancies state a salary |

## Behaviour when a blocking check fails
1. `quality_gate` → `blocked` (deterministic, so not retried). `publish_gold` → `skipped`.
2. Run status `blocked`; an `error` alert goes to `ops_alerts` and `data/logs/alerts.log`.
3. The Gold tables and `gold_publications` remain unchanged, so the last valid dataset stays live.
   This is proven by `test_invalid_data_blocks_publication_and_keeps_last_gold`, which compares the full Gold
   contents before and after for 5 kinds of bad data.
4. Recovery: a newer snapshot with corrected records supersedes the bad version (latest version per id wins).
   The operator can also remove the bad raw file from the landing zone and re-run.

## Results on the real data
* Latest run: all 8 checks passed — 421 records checked for ids, titles, dates (15 without a source date), location and
  PII; 199 records stating a salary checked for valid ranges; 0 failures.
* Real blocked run (2026-11-24 23:13 UTC, run 11): after the live fetch, `valid_dates` failed on 15 postings from employer
  career sites (Yapı Kredi, Ziraat) that publish **no** posting date. Gold v10 stayed live and an error alert was
  written. Analysis: the value was *missing*, not *invalid*; the project preserves missing values elsewhere (salary), so
  the rule was refined to validate present dates and report missing ones. Regression test:
  `test_missing_posting_date_is_published_not_guessed`; invalid dates still block (`test_invalid_data_blocks_publication...`).


## Real case: blocked publication because of an invalid salary (2026-11-24 23:51 UTC)
* Run `20261124T235131Z-0bbb2e` was **blocked** by `valid_salary_ranges`: `work_az:9478` published salary_from 1500 >
  salary_to 600 (AZN). Gold was not replaced; an error alert was written; the website kept the previous version.
* The record was reviewed. A documented, record-level exception in `transform/silver.py` treats this one range as "not
  stated" in Silver (issue code `reviewed_invalid_salary_range_treated_as_not_stated`). The raw file and the Bronze
  record are preserved unchanged.
* Next run `20261124T235704Z-2c8db1`: all 8 checks passed, publication succeeded.
* The rule was **not** weakened: `tests/test_salary_regression.py` asserts that the same values under any other id still
  fail the check, and the failed-validation demo (salary 3000 > 500) is still blocked on the full dataset.

## Practical purpose of each check (also shown in the UI)
| Check | What it prevents |
|---|---|
| unique_normalized_ids | two conflicting records for the same vacancy |
| non_empty_titles | vacancies without a title on the website |
| valid_dates | impossible / future dates distorting timelines |
| valid_salary_ranges | broken ranges (e.g. 1500–600) distorting salary analytics |
| normalized_baku_location | vacancies outside the Baku market |
| no_contact_pii_in_text | publication of detectable personal contacts (e-mails, phones) |
| volume_not_collapsed | publishing an unexpectedly empty or incomplete dataset |
| salary_coverage_info (warning) | silently low salary coverage (warns, does not block) |
