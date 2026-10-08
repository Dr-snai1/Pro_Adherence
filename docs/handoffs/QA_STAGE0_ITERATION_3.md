> **HISTORICAL / SUPERSEDED ROUTING RECORD.** Retained for audit only; it is not a current QA admission or Stage-status source. Current operational status → project `07_STAGE_STATUS`; current admission is governed by `08_PRE_QA_GATE`.

# Handoff — Stage 0 iteration 3: artifact/run/provenance

**ОТ КОГО:** 03 — Разработка  
**КОМУ:** 04 — Тестирование / QA  
**ТЕМА:** Stage 0 — artifact/run/provenance schemas + lineage  
**ТИП:** implementation handoff / independent QA request

**КОНТЕКСТ:** Реализована третья итерация Stage 0 по TECHNICAL_ARCHITECTURE §§4.1, 6.2–6.4, 7.1–7.3. Архитектурные решения не изменялись.

**РЕЗУЛЬТАТ/ЗАПРОС:**  
- `contracts/schemas/provenance.schema.json` — artifact, run, run_input, run_output, code/config/model/environment refs, source_fetch, quality_report, promotion_event, supersession_relation, compute_asset, lineage_query_result.  
- `contracts/schemas/ids.schema.json` расширен typed IDs для provenance refs.  
- `contracts/manifests/minimal_lineage.example.json` — synthetic minimal lineage fixture.  
- `docs/STAGE0_PROVENANCE.md` и `docs/STAGE0_CONTRACTS.md` синхронизированы.

QA request: независимо проверить JSON Schema validity, обязательность immutable artifact, exact code/config/environment refs, immutable model revision/digest, seed policy, compute-asset fields, promotion constraints, computation signature composition, referential integrity и cross-record invariant: один immutable output artifact имеет не более одного producing run.

**ПРОВЕРКА:**  
Developer check A: GitHub readback + structural completeness/invariant audit; passed.  
Developer check B: positive/negative schema cases + separate duplicate-output-producer check; mutable artifact, mutable-name-only model, fixed seed without seed, promoted event without release, and duplicate output producer all rejected as intended.  
Documentation was updated and rechecked after implementation.

**ИСТОЧНИКИ:** TECHNICAL_ARCHITECTURE §§4.1, 6.2–6.4, 7.1–7.3; 01_PROJECT_RULES; 05_DEVELOPMENT_SETUP.

**ЧТО ИЗМЕНИЛОСЬ:** Provenance is now machine-readable and normalized through exact IDs and run bindings. Computation signatures no longer depend on filenames or mtimes.

**ЧТО ОБНОВИТЬ:** QA should record independent acceptance results in its own QA source of truth. No architecture update required unless QA identifies a conflict.

**ОТКРЫТЫЕ ВОПРОСЫ:** Cross-record referential/uniqueness enforcement is specified but the executable repository validator is still a later Stage 0 iteration. Corpus/release manifests are not yet implemented.

**СЛЕДУЮЩЕЕ ДЕЙСТВИЕ:** Independent QA; development proceeds next to corpus/release manifests.
