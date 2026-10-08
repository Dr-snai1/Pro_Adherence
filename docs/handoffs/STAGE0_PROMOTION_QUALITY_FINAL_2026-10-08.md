# Stage 0 promotion-quality implementation handoff — FINAL — 2026-10-08

ОТ КОГО: **временный чат реализации Stage 0**  
КОМУ: **03 — Разработка**  
ТЕМА: **Pro_Adherence — fail-closed PASS-only promotion-quality predicate**  
ТИП: **final implementation handoff / targeted QA routing request**

## КОНТЕКСТ

Repository: `Dr-snai1/Pro_Adherence`.  
Baseline: `main@7723cd83792d5cc4de332ad9add2ea0e5120dfeb`.  
Final implementation commit: `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`.

Authoritative TECHNICAL_ARCHITECTURE resolved the prior promotion-quality ambiguity: exact evidence set, report-status consistency, direct artifact/direct run-output scope, mandatory per-artifact PASS coverage, logical AND aggregation, no WARN/FAIL waiver, rejected events excluded from release promotion.

The pre-decision QA request and architecture-decision request remain in history and are explicitly marked `SUPERSEDED`.

## РЕЗУЛЬТАТ / ЗАПРОС

Implemented the approved predicate:

- `quality_report.status` must equal the effective `fail > warn > pass` aggregate of checks;
- promoted events accept only internally consistent PASS reports listed explicitly in `quality_report_ids`;
- artifact-scoped evidence covers only the identical artifact;
- run-scoped evidence covers only direct `subject_run_id -> run_output -> artifact_id` outputs;
- every promoted artifact needs at least one qualifying PASS report;
- every report in the exact evidence set must be relevant to at least one event artifact;
- WARN, FAIL, PASS+WARN and PASS+FAIL fail closed; no waiver/override exists;
- `compute_asset.quality_report_id` creates no implicit promotion coverage;
- historical reports outside the event evidence set do not block the decision merely because of status;
- rejected events allow internally consistent PASS/WARN/FAIL evidence and incomplete artifact coverage, but each referenced report must be relevant and the event never qualifies for a promoted release;
- a promoted release counts only promotion events that are promoted, target that release and pass the quality predicate; the union of qualifying events must cover every release artifact;
- aggregate `stage0` now executes a deterministic promoted-release smoke through the same predicate.

Request to 03: record `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2` as the current implementation for this workstream and route the prepared targeted QA request to **04 — Тестирование / QA**. **Do not declare Stage 0 PASS.**

## ПРОВЕРКА

### A — exact committed executable suite

Source → GitHub commit `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`.  
Method → GitHub Actions checkout of that exact SHA using committed workflow `.github/workflows/stage0-tests.yml`.  
Result:

- run `37813141576`: **success**;
- job `113434865098`: **success**;
- Python `3.13.16`;
- jsonschema `4.26.0`;
- `python -m unittest discover -s tests -p 'test_*.py'`: **68 tests, OK, 0 failures/errors, exit 0**;
- focused CLI: `contracts`, `corpus`, `release`, `lineage`, `boundary` — **PASS / exit 0**;
- `PYTHONPATH=src python -m pro_adherence.validate stage0` — **PASS / exit 0**;
- `PYTHONPATH=src python scripts/stage0_mutation_audit.py` — **PASS / exit 0**;
- all prior 43-test regressions, including QA-S0-001–005 coverage, remain passing within the 68-test suite.

Interpretation → the final implementation state is executable, preserves previous regressions, and exercises the new predicate in both release tests and aggregate Stage 0 validation.

### B — independent semantic decision audit

Source → deterministic fixture/mutations, separate from the unit-test code path.  
Method → `scripts/stage0_mutation_audit.py`.  
Result → **21/21** injected defects rejected; exact lineage chain PASS; decision matrix **12/12** matched:

- applicable PASS → VALID;
- WARN → INVALID;
- FAIL → INVALID;
- PASS + WARN → INVALID;
- PASS + FAIL → INVALID;
- unrelated PASS → INVALID;
- run PASS → direct output → VALID;
- run PASS → descendant only → INVALID;
- artifact without coverage → INVALID;
- rejected event → not valid promotion;
- inconsistent report status → INVALID;
- release union coverage gap → INVALID.

Interpretation → the promotion gate fails closed on the required semantic corruptions rather than merely validating record shape.

### Final GitHub readback / diff audit

Source → GitHub final implementation tree and comparison to baseline `7723cd...`.  
Method → reread all 10 changed implementation files from `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`, compare commits, cross-check docs ↔ architecture ↔ schema ↔ validator ↔ fixtures ↔ tests ↔ audit.  
Result → baseline→implementation is 2 commits, 10 files, **+804 / -18**, with no file deletions or unrelated paths:

1. `contracts/schemas/provenance.schema.json` +10/-5
2. `docs/STAGE0_PROVENANCE.md` +6/-0
3. `docs/STAGE0_STATUS.md` +4/-2
4. `docs/STAGE0_VALIDATION.md` +3/-1
5. `docs/handoffs/ARCH_PROMOTION_QUALITY_REPORT_DECISION.md` +2/-0
6. `docs/handoffs/QA_STAGE0_VALIDATOR_GATES_REQUEST.md` +2/-0
7. `scripts/stage0_mutation_audit.py` +170/-4
8. `src/pro_adherence/validate.py` +193/-6
9. `tests/fixtures/promotion_quality_cases.json` +41/-0
10. `tests/test_promotion_quality.py` +373/-0

Interpretation → implementation, tests, audit and documentation agree with the authoritative predicate; historical records were retained rather than silently replaced.

## ИСТОЧНИКИ

Authoritative: current `TECHNICAL_ARCHITECTURE §§2.6, 6.2, 6.5, 9.1, 9.5–9.6, Appendix B`; `01_PROJECT_RULES`; `05_DEVELOPMENT_SETUP`; `06_TESTING_QA_SETUP`.

Implementation: `contracts/schemas/provenance.schema.json`; `contracts/schemas/release-manifest.schema.json`; `src/pro_adherence/validate.py`; `tests/test_stage0_validator.py`; `tests/test_promotion_quality.py`; `tests/fixtures/promotion_quality_cases.json`; `scripts/stage0_mutation_audit.py`; `docs/STAGE0_PROVENANCE.md`; `docs/STAGE0_VALIDATION.md`; `docs/STAGE0_STATUS.md`; `.github/workflows/stage0-tests.yml`.

## ЧТО ИЗМЕНИЛОСЬ

Intermediate implementation `1a8ee69606d6640e44ff390e106ecb1d4c949a9d` implemented the predicate and passed CI, but final readback found that aggregate `stage0` did not itself execute a promoted-release case. That state is **SUPERSEDED** by `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`, which adds the aggregate promoted smoke and three extra edge regressions. No historical file was deleted.

## ЧТО ОБНОВИТЬ

03 — Разработка:
- treat `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2` as current implementation source for this workstream;
- use this final handoff and the prepared QA request as current routing records.

04 — Тестирование / QA:
- independently verify `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`, not the superseded pre-decision validator state;
- record targeted PASS/FAIL/BLOCKED without relying on developer CI as acceptance.

## ОТКРЫТЫЕ ВОПРОСЫ

No open architecture question remains for promotion-quality semantics.

Remaining Stage 0 workstreams/risks are outside this implementation:
- environment/lockfile and patch-level reproducible runtime;
- build/materialization and rebuild/restore;
- final end-to-end acceptance;
- independent QA of this implementation;
- `jsonschema.RefResolver` deprecation remains technical hardening debt.

## СЛЕДУЮЩЕЕ ДЕЙСТВИЕ

03 performs its readback of this handoff, records the final implementation SHA, and routes `docs/handoffs/QA_STAGE0_PROMOTION_QUALITY_REQUEST.md` to 04 for targeted independent verification. Overall Stage 0 remains **OPEN / NOT RELEASE-READY**.

## Commit metadata

Final implementation commit SHA: `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`.  
Final handoff commit SHA: **the commit containing this file; exact SHA must be supplied in the chat handoff because a Git commit cannot contain its own SHA without changing itself.**
