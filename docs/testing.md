# Testing

All results below were produced by actually running the commands on 2026-11-25 (Windows 11, Python 3.13.0, Node 22.15.1).

## Automated (Python) — `python -m pytest` → **66 passed** (public release, 2026-11-26)

| File | Tests | What it proves |
|---|---|---|
| `tests/test_transform.py` | 17 | city/date/currency/amount/employment/company normalisation; PII redaction incl. internationalised and obfuscated e-mails; conservative dedup; matcher stems, offsets, case rules, overlap; ESCO alt-label filtering; reviewed false-positive exclusions |
| `tests/test_pipeline.py` | 18 | full pipeline publishes Gold with evidence and no PII; idempotent rerun; 5 kinds of invalid data block publication and keep Gold byte-identical; volume collapse blocks; missing posting date is published as missing (regression); source failure → recovery; API client pagination, incremental params, max pages, quota_exceeded not retried, budget refusal, missing key; backfill range; run lock; task retry |
| `tests/test_incremental.py` | 4 | tie-safe watermark; a tied `ingested_at` batch spanning pages is not skipped (resume cursor + params); rejected cursor falls back to the watermark; salary placeholder / bool edge cases |
| `tests/test_api.py` | 9 | API serves only Gold and no PII/secrets; search, filters, pagination, detail; skills/salary; career match keeps market vs ESCO separate; roadmap score = sum of components; admin endpoints reject non-local clients, missing CSRF header and foreign Origin; 409 on concurrent runs; a blocked run leaves published vacancies unchanged |
| `tests/test_demo.py` | 4 | each reliability demo passes in a sandbox and leaves the main warehouse untouched |
| `tests/test_scheduler.py` | 2 | a failed scheduled run schedules exactly one recovery retry; success schedules nothing |
| `tests/test_filters_labels.py` | 6 | (+ matching vacancies: no fake score without skills, unscored vacancies not ranked, ranking by coverage; comparison never mixes salary groups) |
| | | salary overlap semantics, missing salary never matches, min>max rejected, combined filters and totals over the whole dataset, skill total independent of display limit, local labels + RU/AZ search |
| `tests/test_salary_regression.py` | 1 | reviewed work_az:9478 exception; the same invalid range under another id still fails the check |
| `tests/test_demo_data.py` | 3 | synthetic demo dataset: isolated data dir, clearly marked synthetic, no PII, full pipeline succeeds, API reports demo mode, the live API key is ignored; CLI refuses to generate outside demo mode; failed-validation demo works on freshly timestamped data (regression) |
| `tests/test_frontend_static.py` | 2 | regression guard: no expression-bodied `useEffect` (the navigation bug); routes are wrapped in a keyed error boundary |

Network: none. Live HTTP is replaced by `httpx.MockTransport`; tests use temporary directories and a mini ESCO.

## Frontend

| Check | Result |
|---|---|
| `npm run typecheck` (`tsc --noEmit`, strict) | 0 errors. The RU and AZ resource files are typed against EN, so a missing translation key fails the build |
| `npm run build` | success; JS 848.2 kB (251.0 kB gzip), CSS 30.5 kB |

There is no frontend unit-test framework; the UI was verified in a real browser (below).

## Browser verification (Chrome, production build at http://127.0.0.1:8000)

Performed with scripted clicks and DOM checks in the real browser:

* **Navigation:** sidebar through all 10 pages (1.3 s apart), 30 rapid clicks (80 ms apart), back, back, forward, plus direct
  URLs with full reload. Every page rendered its heading, no full-page reload occurred (a JS marker survived), and the
  console showed **0 errors**. Before the fix the same script reproduced `TypeError: destroy is not a function` and a blank app.
* **Localisation:** RU active when nothing is stored; AZ and EN switch instantly without reload; after a full reload on a
  direct URL the stored language is kept; locale formats checked (`45,3 %`, `2 500`); languages switched mid-navigation
  across all pages with 0 errors.
* **Job Explorer:** 402 results, next page → "2 / 27", keyword → 17 results with URL state, filter chip, drawer with
  10 evidence highlights and the original-posting link.
* **Career Match / Roadmap:** sample badge (n = 14), coverage changes when a skill is ticked (36 % → 51 %), the
  insufficient-data warning for an occupation with n = 4, the not-a-probability statement, translated roadmap reasons,
  checklist persisted. Test changes to the user's saved selection were reverted afterwards.
* **Responsive:** each of the 10 pages loaded in a 375 px-wide viewport (same-origin iframe) and measured: page
  `scrollWidth` = viewport width on all pages after fixing two overflow bugs.

## Backend HTTP smoke (real server)

* 10 page routes and the main API endpoints → 200; unknown `/api/...` → 404 JSON.
* 400 concurrent requests across 12 endpoints → 400 × HTTP 200 (Phase 2, after fixing a SQLite threading bug).
* Admin over HTTP: no header → 403, foreign Origin → 403, live fetch without confirmation → 400, run → 202 then success,
  second run during a scheduled run → 409.
* Server not reachable from the machine's LAN IP (bound to 127.0.0.1).

## Not tested

Docker/compose (Docker not operational), real phones/tablets, Firefox and Safari, screen readers, very large datasets.


## Final release verification (2026-11-25, real Chrome, production build, full dataset)
* After the Python changes the server was restarted; then, from the Operations page: web ETL (success, 7.12 s),
  concurrent run → 409, all four demos PASSED on the full 1,621-record sandbox copy, scheduler "Enable + run now"
  (scheduled run success 7.74 s, 409 during it), scheduler stopped. Working Gold fingerprint identical before/after demos.
* 10 pages × RU/AZ/EN via sidebar: 30/30 rendered, 0 console errors; 375 px: no horizontal overflow on all 10 pages.
* Job Explorer filter scenario and Career Match (sales manager, accountant, shop assistant) — see final-results.md §10.
* Website metrics equal database metrics (vacancies, skills, matches, salaries) — final-results.md §6.
