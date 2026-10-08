> **STATUS: SUPERSEDED.** Independent QA completed this targeted executable rerun: promotion-quality semantics passed, but QA-S0-006 remained open because `docs/STAGE0_MANIFESTS.md` contained stale current documentation. Use the subsequent QA-S0-006 documentation-rerun request for final closure. Preserve this request as audit history.

# Handoff — Stage 0 promotion-quality targeted independent QA request

ОТ КОГО: **03 — Разработка (prepared for routing by temporary implementation chat)**  
КОМУ: **04 — Тестирование / QA**  
ТЕМА: **Pro_Adherence — QA-S0-006 promotion-quality targeted verification**  
ТИП: **independent QA acceptance request**

## КОНТЕКСТ

Target implementation: `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`.  
Baseline before this workstream: `7723cd83792d5cc4de332ad9add2ea0e5120dfeb`.

The previous `QA_STAGE0_VALIDATOR_GATES_REQUEST.md` is **SUPERSEDED** because it explicitly described the pre-architecture behavior in which PASS-only semantics were unresolved. The architecture question is now closed and the executable validator has changed.

QA-S0-001–005 remain previously CLOSED. QA-S0-006 is implemented and pending this targeted rerun. QA-S0-007, QA-S0-008 and QA-S0-009 remain OPEN / BLOCKING and are explicitly outside this implementation scope. Overall Stage 0 remains **OPEN / NOT RELEASE-READY**.

## РЕЗУЛЬТАТ / ЗАПРОС

Independently verify at `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`:

- report-level `fail > warn > pass` status consistency;
- exact promotion evidence set and PASS-only logical AND;
- WARN/FAIL blocking with no waiver;
- artifact scope = identical artifact only;
- run scope = direct `run_output` only, with descendants/inferred links rejected;
- complete per-artifact qualifying coverage;
- unrelated extra report rejection;
- no implicit `compute_asset.quality_report_id` coverage;
- historical unreferenced FAIL does not automatically block a current valid promotion;
- rejected event provenance rules and exclusion from release promotion;
- promoted release target matching and union coverage;
- existing lineage/publication/corpus gates and QA-S0-001–005 regressions;
- aggregate `stage0` actually executes the promoted-release smoke.

Do not use developer CI as QA acceptance evidence; reproduce independently.

## ПРОВЕРКА

Developer evidence for comparison only:
- GitHub Actions run `37813141576`, job `113434865098`: success on exact SHA `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`;
- Python 3.13.16; jsonschema 4.26.0;
- 68 tests OK;
- focused CLI and aggregate `stage0` PASS;
- 21/21 semantic mutations rejected;
- independent developer decision matrix 12/12 matched.

QA should construct its own positive/negative cases and report discrepancies rather than selecting the convenient result.

## ИСТОЧНИКИ

Current `TECHNICAL_ARCHITECTURE §§2.6, 6.2, 6.5, 9.1, 9.5–9.6, Appendix B`; `01_PROJECT_RULES`; `05_DEVELOPMENT_SETUP`; `06_TESTING_QA_SETUP`; final implementation `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`; current Stage 0 schema/validator/tests/audit/docs.

## ЧТО ИЗМЕНИЛОСЬ

Promotion semantics are no longer architecture-blocked. The validator now enforces report consistency, exact PASS-only evidence, direct scope, per-artifact coverage, rejected-event exclusion and release union coverage. Aggregate `stage0` includes a deterministic promoted-release smoke.

## ЧТО ОБНОВИТЬ

04 should update the Stage 0 QA matrix and return a targeted verdict specifically for QA-S0-006. Do not infer closure of QA-S0-007–009 from this rerun. If any semantic conflict is found against the authoritative architecture, escalate the conflict rather than weakening the gate.

## ОТКРЫТЫЕ ВОПРОСЫ

None for the normative promotion-quality predicate. QA-S0-007 (lineage cycle detection), QA-S0-008 (fail-closed public/research boundary), and QA-S0-009 (clean-checkout bare CLI/install contract) remain OPEN / BLOCKING and require separate implementation. Environment/lockfile, materialization/rebuild and final E2E remain separate Stage 0 acceptance areas.

## СЛЕДУЮЩЕЕ ДЕЙСТВИЕ

04 independently verifies QA-S0-006 at `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2` and returns evidence-backed PASS/FAIL/BLOCKED to 03. QA-S0-007–009 remain outside this rerun and stay OPEN / BLOCKING until separately fixed and independently verified. **Do not declare overall Stage 0 PASS from this targeted workstream alone.**
