# Handoff — Stage 0 QA-S0-001–004 fixes: scoped QA rerun request

**ОТ КОГО:** 03 — Разработка  
**КОМУ:** 04 — Тестирование / QA  
**ТЕМА:** Pro_Adherence — Stage 0: повторная независимая проверка QA-S0-001–004  
**ТИП:** QA rerun request / blocking defect verification

**КОНТЕКСТ:**  
Независимый QA Stage 0 ранее выдал FAIL. Временный чат реализации исправил QA-S0-001–004 в commit `954c7a8ec6864941d018509ee27f70dce7832535`; handoff зафиксирован commit `b8d5c0dd29cb06d46cb49b2b743e0a623c7f27a1`. Текущий `main` указывает на `b8d5c0dd29cb06d46cb49b2b743e0a623c7f27a1`. QA-S0-005 намеренно не изменён и остаётся blocking pending architecture decision.

**РЕЗУЛЬТАТ / ЗАПРОС:**  
Просьба независимо rerun только defects QA-S0-001–004 и связанные regression criteria.

- QA-S0-001: provenance root records имеют обязательный unique `record_type`; `run_input` и `run_output` должны проходить root validation и совпадать ровно с одной `oneOf` alternative.
- QA-S0-002: добавлен `lineage_bundle`; `contracts/manifests/minimal_lineage.example.json` должен валидироваться как единый fixture и содержать минимально полный lineage.
- QA-S0-003: добавлены versioned identity-resolution events для `alias`, `merge`, `split`, `supersession`; legacy `article.superseded_by` сохранён, но документирован как deprecated for complete history.
- QA-S0-004: `immutable_version_ref` отклоняет mutable aliases (`latest/current/HEAD/main/master/...`); corpus schema/resolver и release artifact schema versions используют exact immutable refs.

**ПРОВЕРКА:**  
Developer verification 03 completed:
1. GitHub diff/readback against baseline `faa27e0693eee7a2794b8ff6248d192f2b1a9174`; affected files and migration documentation are present on current main.
2. Independent targeted executable schema/invariant check against current GitHub JSON passed:
   - run_input root PASS and exactly one alternative;
   - run_output root PASS and exactly one alternative;
   - lineage_bundle PASS; incomplete bundle without environment_refs FAIL;
   - identity history fixture PASS and contains alias/merge/split/supersession;
   - all tested mutable aliases FAIL immutable-version contract;
   - concrete immutable versions PASS;
   - corpus `latest` mutations FAIL;
   - release artifact `schema_version=latest` FAIL;
   - lineage fixture internal run/artifact/code/config/model/environment references resolve and output has a single producer.

The committed Python regression suite is `tests/test_stage0_contract_regressions.py`. It was syntax/readback reviewed, but **03 could not execute that exact Python suite in its local runtime because the runtime cannot resolve github.com to materialize the repository**. This limitation is explicit and must not be interpreted as a passing Python test result. QA should execute it independently.

**ИСТОЧНИКИ:**  
- Google Drive: `STAGE0_INDEPENDENT_QA_2026-10-08`
- `TECHNICAL_ARCHITECTURE`
- `01_PROJECT_RULES`
- `05_DEVELOPMENT_SETUP`
- `06_TESTING_QA_SETUP`
- GitHub commits `954c7a8ec6864941d018509ee27f70dce7832535`, `b8d5c0dd29cb06d46cb49b2b743e0a623c7f27a1`
- `tests/test_stage0_contract_regressions.py`
- `docs/STAGE0_CONTRACT_MIGRATION_2026-10-08.md`

**ЧТО ИЗМЕНИЛОСЬ:**  
Исправлены только QA-S0-001–004; обновлены schemas, fixtures, regression tests и Stage 0 contract documentation. QA-S0-005 не тронут.

**ЧТО ОБНОВИТЬ:**  
04 — QA должен обновить defect register и acceptance matrix по QA-S0-001–004 после независимого rerun. Финальный Stage 0 verdict не выдавать как PASS, пока QA-S0-005 и остальные blocked acceptance criteria не закрыты.

**ОТКРЫТЫЕ ВОПРОСЫ:**  
QA-S0-005 — immutable model identity in computation_signature — остаётся blocking и ожидает решения 02 — Техническая архитектура. Executable repository validator/build flow также остаётся отдельной незавершённой частью Stage 0.

**СЛЕДУЮЩЕЕ ДЕЙСТВИЕ:**  
04 — Тестирование / QA независимо выполняет committed Python regression suite и повторяет свои reproduction checks для QA-S0-001–004; затем возвращает PASS/FAIL по каждому defect в 03 — Разработка. Stage 0 overall остаётся open.
