# Skill & occupation extraction

## Method (no ML; every result can be explained)
1. **Dictionary.**
   * ESCO English preferred and alt labels for 13,939 skills (1–6 tokens).
   * Curated aliases in `skillradar/skills/resources/skill_aliases.csv` (89 entries, AZ/RU/EN) and
     `occupation_aliases.csv` (60). Each alias points to an ESCO **preferred label**. It is loaded only if that
     label exists in the CSV; otherwise it is rejected and reported (0 rejected on ESCO v1.2.0).
2. **Folding.** Text and labels are lower-cased and stripped of diacritics one character at a time
   (`ə→e, ı/İ→i, ş→s, ç→c, ğ→g, ö→o, ü→u`). The folded string keeps the original length, so offsets of a
   match point to the exact original characters.
3. **Matching.**
   * Exact labels sit in a hash map keyed by their token tuple. Each text position needs about 6 lookups, so a
     scan costs O(tokens × 6).
   * Alias tokens ending in `*` are stems that absorb Azerbaijani/Russian suffixes
     (`satış*` → *satışda, satışın*; `английск*` → *английского*). Stems are indexed by their first 3 letters.
   * Labels of ≤ 4 characters (SQL, SAP, HSE, CRM) must appear in UPPER CASE.
   * Overlaps: the longest span wins.
4. **Evidence.** Each match is stored in `silver_job_skills` with field (title/description/requirements),
   start/end offsets, the exact matched text, the dictionary label, its type (preferred/alt/alias), its language and a snippet.
5. **Unknown ≠ absent.** Vacancies without description/requirements get `skill_status = 'no_text'` (19 of 100).
   Gold shares (`share_of_text_pct`) use as denominator only vacancies that have text or evidence,
   never all vacancies.

## Noise controls (from inspecting real matches)
Inspecting the first extraction on the real corpus revealed these false positives, each fixed by a rule:

| Observation | Fix |
|---|---|
| ESCO single-word **alt** labels map to surprising concepts: `security` → *securities*, `standard` → *scaffolding components*, `reporting` → *journalism*, `banking` → *economics* | drop single-word alt labels, except short upper-case acronyms (874 dropped) |
| alt labels shared by several concepts | dropped as ambiguous (448) |
| `AR` matched "Azərbaycan Respublikası" (ESCO: augmented reality); `IT` → *computer technology*; `logging` = forestry | stoplist `{ar, it, logging}` |
| `Email` matched our own `[EMAIL]` redaction marker | placeholders are blanked before matching |

## Result on the real data
393 evidence rows, 44 distinct ESCO skills, 74 vacancies with ≥ 1 skill.
By label type: 371 alias, 14 ESCO preferred, 8 ESCO alt. In other words, the curated multilingual aliases
drive the results, which is expected for a corpus that is ~70 % Azerbaijani while ESCO is English-only.

Top skills (canonical vacancies): assume responsibility 37, work in teams 25, sales activities 20, English 17,
Russian 17, use microsoft office 16, use spreadsheets software 14, Azerbaijani 12.

Occupations: 35 titles mapped (32 canonical), e.g. sales manager 8, accountant 5, technical sales representative 4.

## Limitations
* Precision was judged by manually inspecting the matched texts on this 100-posting corpus. There is no labelled
  test set, so no precision/recall figures are claimed.
* Aliases were drafted with AI assistance, validated automatically against ESCO label existence and
  reviewed against real matches. They were not reviewed by a labour-market domain expert.
  Some mappings are interpretive (e.g. *məsuliyyətli* "responsible" → ESCO *assume responsibility*).
* Skills missing from ESCO (1C accounting software, CorelDraw) are not extracted, because inventing URIs is not allowed.


## Final review on the expanded corpus (Phase 3, 421 records)

Every non-alias match and every occupation mapping was reviewed against the real text. Removed because the real
context showed a wrong concept:

| Text in vacancies | Was mapped to | Fix |
|---|---|---|
| "deployment **history**", "credit history" | ESCO *history* (academic subject) | stoplist |
| "**polish**" (verb) | *Polish* (language) | stoplist |
| "**POS**-terminal" | *blockchain consensus mechanisms* | stoplist |
| "**NOC** environments" | *tools for software configuration management* | stoplist |
| "passion for **crafting** UIs" | *crafting* (handicraft) | stoplist |
| "vendor **ecosystems**" | *ecosystems* | stoplist |
| "server **migration**" | *migration* (human) | stoplist |
| "**energy** and utilities sector" | *energy* (physics knowledge) | stoplist |
| "**CFD**" (contract for difference, finance) | *computational fluid dynamics* | stoplist |
| title "Planning Engineer" (project scheduling) | occupation *land planner* | excluded ESCO alt label |
| "Site **Reliability Engineer**" | *dependability engineer* | excluded ESCO alt label |
| "Middle **System Engineer**" | *ICT network technician* | excluded ESCO alt label |
| "Middle **QA Engineer**" (software) | *quality engineer* (manufacturing) | excluded ESCO alt label |
| "Xadimə" (office cleaner) | *domestic cleaner* (private households) | alias → *building cleaner* |
| "Satış təmsilçisi" (sales rep) | *technical sales representative* | alias → *commercial sales representative* |

Kept after review (correct in context): *R* ("R, Python"), *TLS*, *IAM*, *DNS*, *NN* (neural networks in an ML
posting), *economics* ("degree in Economics"), *SQL*, *CRM*. Regression test:
`test_reviewed_false_positive_labels_are_excluded`.

### Result after the review (Gold v15)
211 distinct skills, 2,458 published evidence matches (alias 1,316 · ESCO preferred 833 · ESCO alt 309);
355 of 402 vacancies with at least one skill, 30 with text but no match, 17 without text (unknown).
128 vacancies (31.8 %) mapped to 52 ESCO occupations.

### Language of labels in the UI
ESCO v1.2.0 publishes no Russian or Azerbaijani labels, so skills and occupations are displayed with their official
English labels in all three UI languages (marked "ESCO · EN"). No label is machine-translated; identifiers (URIs) are
never modified.

### Career Match reliability rules (Phase 3)
* Market evidence and ESCO evidence are separate columns and separate scores.
* Every market score shows its sample size (n = vacancies mapped to the occupation).
* Fewer than 5 mapped vacancies → an "insufficient market data" warning on Career Match and the Roadmap.
* Scores are labelled as skill-list coverage, explicitly **not** a hiring probability.
