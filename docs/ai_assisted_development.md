# AI-Assisted Development Declaration

SkillRadar is an **AI-assisted academic development project**. It was built between 2026-11-24 and 2026-11-26 with an
AI coding assistant (Claude Code, model Claude Opus 5.5) working in the project directory, directed by the project
author through a sequence of written requirement documents (five development phases plus this public release).

## Division of work

| The author | The AI assistant |
|---|---|
| Chose the problem, the target users and the data sources | Profiled the input data before writing code |
| Wrote the requirements for every phase and the acceptance criteria | Wrote the Python and TypeScript code, the SQL schema, the tests and most of the documentation |
| Decided on data-usage questions and approved every live API budget use | Ran the pipeline, the tests, the build and the browser checks, and reported the measured numbers |
| Tested the application functionally and reported problems (e.g. pages needing a manual refresh, a skills counter showing 200 instead of 340, unclear career metrics) | Reproduced the reported problems, found root causes and implemented fixes with regression tests |
| Reviewed a suspicious salary record and decided how it should be handled (reviewed exception `work_az:9478`, with its own regression test) | Implemented the exception exactly as specified |
| Verified fixes and accepted the final product | Prepared the public release: synthetic demo dataset, screenshots, these documents |

The author does **not** claim to have written the code by hand or to be an expert in every technology the project
uses. The skills the author practised are product definition, requirements writing, directing AI-assisted
development, data and result analysis, functional testing and fix verification.

## How correctness was checked

* Every number in the README and in `docs/` comes from a recorded run of the pipeline, the test suite or a SQL query
  on the warehouse; no pipeline history was simulated (`ops_pipeline_runs` holds only real executions).
* 66 automated tests run without network access; live HTTP is replaced by a mocked transport.
* The UI was checked in a real Chrome browser with scripted navigation (desktop width); phone width only partially.

## What the AI produced that needs human review

* **Translations.** The Russian and Azerbaijani UI texts and the RU/AZ labels for ESCO skills and occupations
  (`skillradar/skills/resources/label_translations.psv`) were written by the AI assistant. They are not official ESCO
  translations and have not been reviewed by a professional translator.
* **Alias lists.** The multilingual skill/occupation aliases were drafted by the assistant; every target label was
  checked automatically against the ESCO CSV, and false positives found in real matches were removed
  (`docs/skill_extraction.md`). Precision and recall have not been measured.
* **Synthetic demo data** (`skillradar/demo_data.py`) is invented by design and must never be read as market data.

## Live API use

The Softon free plan allows 100 requests per month. The warehouse logs 17 live requests (account quota afterwards:
20 / 100). The live fetch is never started automatically: it requires an explicit command, and live requests were
made only on the author's instruction. Tests, the scheduler in the UI and the demonstrations never call the live API.

## Data protection decisions

* Contact e-mails and phone numbers are removed or redacted at ingestion and re-checked by a blocking quality check.
* Real company and contact data that had been copied into test fixtures during development was replaced with
  fictional values.
* Raw Softon data, the warehouse database and the ESCO files are not published (see `docs/data_sources.md`). The
  public repository was created with a fresh history.
