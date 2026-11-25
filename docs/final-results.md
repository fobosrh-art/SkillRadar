# SkillRadar — final results (measured 2026-11-25)

All numbers were read from `data/warehouse/skillradar.db` or produced by commands executed on the development
machine (Windows 11, Python 3.13.0, Node 22.15.1). Nothing is estimated or simulated. **Operational history is
short:** all runs happened between 2026-11-24 22:03 UTC and 2026-11-25 07:41 UTC; there is no multi-week history.

## 1. Data volumes (Gold v21)

| Measure | Value |
|---|---|
| Raw vacancy records (Bronze) | **1,621** from 18 raw files (1 provided export + 17 live API snapshots, 2026-11-24 … 2026-11-25) |
| Silver vacancies | **1,515** (newest version per Softon id) |
| Cross-source duplicates (flagged, not deleted) | 314 |
| **Published, deduplicated vacancies (Gold)** | **1,201** |
| Employers / vacancy sources | **667 / 28** |
| ESCO occupations mapped in published vacancies | **80** |
| Distinct ESCO skills found | **340** |
| Published skill-evidence matches | **6,422** |
| Vacancies with a published salary | 420 (AZN, period not stated 273; AZN monthly 147) |
| Source posting dates | 2025-08-13 → 2026-11-24 (64 distinct days); 15 vacancies without a posting date (kept missing) |
| Live API requests logged | 17 (account quota after the last one: 20 / 100) |

## 2. ESCO reference data
3,039 occupations · 13,939 skills · 128,987 occupation–skill relations (ESCO v1.2.0, English).

## 3. Local RU/AZ translations of ESCO labels (SkillRadar's own, not official ESCO translations)

| Scope | Translated |
|---|---|
| Skills present in the published vacancies | **340 / 340 (100 %)** |
| Occupations present in the published vacancies | **80 / 80 (100 %)** |
| Essential ESCO skills of sales manager / accountant / shop assistant | 42/42 · 26/26 · 22/22 |
| Optional ESCO skills of those occupations | 7/20 · 3/31 · 2/13 (rest fall back to English) |
| Whole ESCO classifier | 417 / 13,939 skills (3 %) · 80 / 3,039 occupations (2.6 %) |

Stored in `skillradar/skills/resources/label_translations.psv`, resolved to ESCO URIs at load time; ESCO data,
URIs, matching and analytics are unchanged. Translations are AI-assisted and were not reviewed by a professional
translator. Untranslated concepts are shown with their official English label.

## 4. Pipeline execution history (all real)
23 runs: **21 success, 2 blocked, 0 failed**. Triggers: CLI 16, web 4, scheduler 3.

Real blocked runs (the previous Gold stayed live in both cases):
1. `20261124T231351Z-6ca2cb` — `valid_dates`: 15 employer postings without a posting date. The rule was refined
   (a missing date is kept missing, a present date must be valid).
2. `20261124T235131Z-0bbb2e` — `valid_salary_ranges`: `work_az:9478` published salary_from 1500 > salary_to 600.
   After review, a documented record-level exception treats that range as "not stated" in Silver (the raw/Bronze record
   is preserved; issue code `reviewed_invalid_salary_range_treated_as_not_stated`; test `test_salary_regression.py`).
   The next run `20261124T235704Z-2c8db1` passed all checks and published. The rule itself was **not** weakened: any
   other record with from > to still blocks (asserted in the same test and in the failed-validation demo).

Latest runs: web ETL `20261125T073820Z-930854` 7.12 s; scheduled `20261125T074057Z-391d0b` 7.74 s.
Average task time on the full dataset: extract_skills 5.26 s · build_silver 1.21 s · quality_gate 0.55 s ·
publish_gold 0.30 s · ingest_esco 0.07 s · ingest_raw 0.03 s.

## 5. Data quality (latest run): 8 / 8 passed
unique_normalized_ids, non_empty_titles, valid_dates, normalized_baku_location, no_contact_pii_in_text (1,515 checked
each), valid_salary_ranges (522 rows stating pay), volume_not_collapsed, salary_coverage_info (warning-level).

## 6. Consistency between the website and the database (checked over HTTP)
| Metric | DB | Overview | Other page |
|---|---|---|---|
| Published vacancies | 1,201 | 1,201 | Job Explorer 1,201 |
| Distinct skills | 340 | 340 | Skills Analytics 340 (was 200: display limit counted as total — fixed) |
| Evidence matches | 6,422 | 6,422 | Skills Analytics 6,422 |
| Vacancies with salary | 420 | 420 | Salary Analytics 420 |

## 7. Safe demonstrations — run from the web UI (Operations page) on the full dataset, all PASSED

| Demo | Evidence (sandbox copy of all 1,621 raw records) |
|---|---|
| Re-run without duplicates (idempotency) | run 2: Bronze 1,621 → 1,621; Gold hash unchanged (`1849e614d0488582`), version 1 → 2 |
| Protection from wrong data (failed validation) | injected 3000 > 500 on work_az:9505 → blocked by valid_salary_ranges; hash/version unchanged; alert 0 → 1; corrected record → v2 |
| Re-processing saved history (backfill) | available snapshot dates 2026-11-24, 2026-11-25; empty range → blocked (empty data never published); real dates → published; repeat → identical hash |
| Source failure & recovery | mock HTTP 503 → 4 attempts, fetch failed, Gold unchanged, alert; recovery after 2 transient errors → success, Bronze 1,621 → 1,626, v2 |

Working warehouse before and after the four demos: Gold v20, hash `1849e614d0488582`, 22 runs — **unchanged**.

## 8. Scheduler and locking (verified through the web UI)
"Enable + run now" → scheduled run `20261125T074057Z-391d0b` (trigger `scheduler`, success, 7.74 s), next run
+6 h recorded; a manual run during it → HTTP 409; "Stop scheduler" → disabled. A manual run requested during the
web ETL → HTTP 409. Scheduled runs process local data only; live API ingestion is never scheduled.

## 9. Tests and builds
| Check | Result |
|---|---|
| `python -m pytest` | **62 passed** |
| `npm run typecheck` | 0 errors |
| `npm run build` | success; JS 868.0 kB (257.5 kB gzip), CSS 30.6 kB |

## 10. Browser verification (Chrome, production build)
* 10 pages × 3 languages via the sidebar without reload: 30/30 rendered, 0 console errors.
* 375 px viewport: all 10 pages without horizontal overflow.
* Job Explorer: 1,201 → salary 800–1,500 AZN: 240 → monthly only: 73 → "lowest salary first" starts 400–800 (overlaps
  800) → page 2/5 → changing a filter resets to page 1/16 → "from" > "to" shows a message and is not applied →
  impossible range shows the empty-result message → "Reset all filters" restores 1,201.
* Career Match (sales manager, n = 49): Russian labels in both columns, sample badge, not-a-probability note.
* Not verified: real phones, Firefox/Safari, Docker.


## 11. Final product improvements (2026-11-25, after commit 8390bea; restore point: tag `stable-8390bea`)
* **Vacancies that suit you** (Career Match, `POST /api/career/jobs`): published Gold vacancies of the chosen occupation
  ranked by coverage = matched / skills extracted from that vacancy. Vacancies without extracted skills are counted but
  never ranked; with no user skills every score is 0 (no fake high rating); vacancies with < 3 detected skills are
  flagged "weak evidence". Shows title, employer, salary (period), source, original link, matched / missing skills,
  full description. Verified in Chrome (sales manager, 3 skills): 49 of 49 vacancies scored, RU/AZ/EN labels.
* **Compare two occupations** (`POST /api/career/compare`): sample size, user coverage, top skills, missing skills,
  common skills, salary medians per (currency, period) group with n. Verified: sales manager (n = 49, 39 %) vs
  accountant (n = 44, 16 %), found via Russian search "бухгалт".
* **Translations:** all optional ESCO skills of sales manager, accountant and shop assistant translated (51 more labels);
  local labels now cover 468 skills + 80 occupations. Still not official ESCO translations.
* **Learning plan CSV export** (UTF-8 with BOM, `;` separated: skill, original ESCO label, priority, score, vacancies,
  ESCO relation, reason, status). Button verified in the UI; the downloaded file itself was not opened during testing.
  Export of filtered job-search results was **not** implemented.
* **"How to use SkillRadar"** 3-step block on the Overview page (RU/AZ/EN).
* Checks completed: learning-plan progress survives reload and occupation switches (separate per occupation);
  Salary Analytics groups equal Job Explorer salary filters and DB medians (AZN unspecified 273 / median floor 700;
  AZN monthly 147 / 600); 0 zero salaries in Gold.
* Final verification after backend restart: **63 tests passed**, TypeScript 0 errors, production build OK; all four
  demos PASSED via the web API on the full 1,621-record dataset; working Gold unchanged (hash `1849e614d0488582`,
  v21, 23 runs before and after); 10 pages without console errors; 375 px without overflow on Overview, Career,
  Roadmap, Jobs.
