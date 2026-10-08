# Handoff — Stage 0 validator/gates independent QA request

**ОТ КОГО:** 03 — Разработка  
**КОМУ:** 04 — Тестирование / QA  
**ТЕМА:** Pro_Adherence — Stage 0 executable validator/gates  
**ТИП:** independent QA acceptance request

**КОНТЕКСТ:**  
Validator/gates workstream implemented from baseline `feaec13035d5d833b4746ea55a025a5c495ef92b`. Implementation code commit: `293ef214cddb132e32b339d2baf0a4938a6e531c`. Current main: `982a66f61cf8ba161ae5c818c58c979d4c2a114e`; commits after implementation only finalize status/validation/handoff documentation and do not change validator code/schema/tests.

QA-S0-001–005 remain independently CLOSED. Stage 0 remains OPEN / NOT RELEASE-READY.

**РЕЗУЛЬТАТ / ЗАПРОС:**  
Independently verify current main for Stage 0 validator/gates:
- offline Draft 2020-12 schema validation and local cross-file refs;
- cross-record referential integrity;
- unique producing-run invariant;
- deterministic complete lineage reconstruction;
- corpus manifest article-count/input-policy/hash reconciliation;
- release exact artifact/hash/schema/type/access/corpus compatibility;
- promotion evidence target/coverage/existence + validated complete lineage;
- explicit release-manifest serving boundary;
- direct-helper mutable model revision alias rejection;
- tracked-tree research/restricted/secret boundary;
- CLI modes `contracts`, `corpus`, `release`, `lineage`, `boundary`, `stage0`;
- regression QA-S0-001–005.

Do not require `quality_report.status = pass` yet: that exact promotion semantic is unresolved and routed to 02 — Техническая архитектура. Verify that current implementation checks quality-report existence but does not silently invent pass-only semantics.

**ПРОВЕРКА:**  
Developer evidence only, not QA acceptance:
- GitHub Actions run `37803936823`, exact implementation SHA `293ef214cddb132e32b339d2baf0a4938a6e531c`: success;
- Python 3.13.16; jsonschema 4.26.0;
- full unittest suite: 43 tests, OK, exit 0;
- focused CLI modes PASS;
- aggregate `stage0` PASS;
- independent mutation audit: 11/11 injected semantic defects rejected; exact lineage chain PASS.
03 independently read back run logs and confirmed these claims.

**ИСТОЧНИКИ:**  
`TECHNICAL_ARCHITECTURE §§6.2–6.5, 7.1–7.3, 9.1, 9.5–9.6, 12.1, Appendix B`; `01_PROJECT_RULES`; `05_DEVELOPMENT_SETUP`; `06_TESTING_QA_SETUP`; `STAGE0_INDEPENDENT_QA_2026-10-08`; repository current main and `docs/STAGE0_STATUS.md`.

**ЧТО ИЗМЕНИЛОСЬ:**  
Executable validator, CLI, policy schema, validator tests, mutation audit, CI integration and current Stage 0 validation documentation were added/updated. No historical handoff/migration record was deleted.

**ЧТО ОБНОВИТЬ:**  
04 should record independent PASS/FAIL/BLOCKED per validator/gate criterion and update the Stage 0 QA matrix. A criterion that depends specifically on unresolved quality-report status semantics should be marked BLOCKED by architecture decision, not guessed.

**ОТКРЫТЫЕ ВОПРОСЫ:**  
Quality-report promotion status semantics are routed separately to 02. Environment/lockfile, build/materialization and final E2E Stage 0 acceptance remain open.

**СЛЕДУЮЩЕЕ ДЕЙСТВИЕ:**  
04 independently executes/reproduces validator/gates on `main@982a66f61cf8ba161ae5c818c58c979d4c2a114e`, checks that validator code/tests match implementation commit `293ef214…`, and returns verdict/evidence to 03. Do not declare overall Stage 0 PASS.
