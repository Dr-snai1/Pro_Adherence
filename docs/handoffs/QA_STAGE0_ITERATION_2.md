> **HISTORICAL / SUPERSEDED ROUTING RECORD.** Retained for audit only; it is not a current QA admission or Stage-status source. Current operational status → project `07_STAGE_STATUS`; current admission is governed by `08_PRE_QA_GATE`.

# Handoff — Stage 0 iteration 2: IDs, entities, access/license

**ОТ КОГО:** 03 — Разработка  
**КОМУ:** 04 — Тестирование / QA  
**ТЕМА:** Stage 0 — ID/entity schemas + access/license classes  
**ТИП:** implementation handoff / independent QA request

**КОНТЕКСТ:** Реализована вторая итерация Stage 0 по TECHNICAL_ARCHITECTURE. Архитектурные решения не изменялись.

**РЕЗУЛЬТАТ/ЗАПРОС:**  
- `contracts/schemas/ids.schema.json` — lowercase UUIDv7 internal surrogate IDs; external identifiers separate.  
- `contracts/schemas/entities.schema.json` — article, article_external_id, article_source_record, author, authorship, affiliation, author_affiliation, source, venue, citation_edge.  
- `contracts/schemas/access-license.schema.json` — access classes: public / project-internal / restricted-license / secret; explicit publication permissions and default-deny constraints.  
- `contracts/policies/access_license_policy.v1.json` — promotion/access policy registry.  
- `docs/STAGE0_CONTRACTS.md` and updated `docs/DIRECTORY_CONVENTIONS.md`.

QA request: independently test schema validity, ID constraints, entity exclusivity, source-vs-venue separation, unresolved identities, citation target exclusivity, default-deny license behavior, and documentation consistency.

**ПРОВЕРКА:**  
Developer check A: GitHub readback + structural/invariant checks; all passed.  
Developer check B: independent mutation/acceptance cases; UUIDv4 rejected, UUIDv7 accepted, unknown-license raw publication rejected, secret publication rejected, dual author identity rejected, dual citation target rejected; all passed.  
Documentation rechecked after update; consistent.

**ИСТОЧНИКИ:** TECHNICAL_ARCHITECTURE §§3.2–3.7, 8.7, Appendix A; 01_PROJECT_RULES; 05_DEVELOPMENT_SETUP.

**ЧТО ИЗМЕНИЛОСЬ:** Stage 0 now has executable machine-readable contracts for IDs/entities/access-license. Directory documentation updated from future tense to implemented state.

**ЧТО ОБНОВИТЬ:** QA should record independent acceptance results in its own QA source of truth. No architecture document change is required unless QA finds a conflict.

**ОТКРЫТЫЕ ВОПРОСЫ:** None in this iteration. Concrete provider-specific legal license classes remain intentionally undefined until source/license evidence exists.

**СЛЕДУЮЩЕЕ ДЕЙСТВИЕ:** Independent QA; development proceeds next to artifact/run/provenance schemas after iteration boundary.
