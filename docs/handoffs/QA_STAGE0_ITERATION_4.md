# Handoff — Stage 0 iteration 4: corpus/release manifests

**ОТ КОГО:** 03 — Разработка  
**КОМУ:** 04 — Тестирование / QA  
**ТЕМА:** Stage 0 — corpus/release manifests  
**ТИП:** implementation handoff / independent QA request

**КОНТЕКСТ:** Реализована четвёртая итерация Stage 0 по TECHNICAL_ARCHITECTURE §§2.4, 6.5, 12.1. Архитектурные решения не изменялись.

**РЕЗУЛЬТАТ/ЗАПРОС:**  
- `contracts/schemas/corpus-release.schema.json` — exact corpus composition, schema/resolver versions, inclusion/exclusion policy refs, exact input artifact hashes, article count, lifecycle status and manifest hash.  
- `contracts/schemas/release-manifest.schema.json` — exact public serving artifacts by artifact ID/content hash/schema version/role/public path and access/license policy.  
- `contracts/manifests/empty_corpus.manifest.json` — valid empty draft corpus fixture.  
- `contracts/manifests/empty_release.manifest.json` — valid empty draft release fixture.  
- `contracts/manifests/policies/empty-inclusion.json` and `empty-exclusion.json` — resolvable empty policy fixtures with content hashes.  
- `docs/STAGE0_MANIFESTS.md` and `docs/STAGE0_CONTRACTS.md` synchronized.

QA request: independently validate JSON Schemas and fixtures; verify promoted release gate; exact artifact versioning; no "latest" semantics; public access/license enforcement; publication-permission basis; manifest hash algorithm; policy-ref content hashes; article_count reconciliation; supersession rules.

**ПРОВЕРКА:**  
Developer check A: GitHub readback + architectural invariant audit; passed.  
Developer check B: JSON Schema Draft 2020-12 validation using jsonschema 4.26 with positive/negative cases; empty draft corpus/release valid; promoted empty invalid; valid public promoted artifact accepted; restricted public artifact and raw-text publication without allow rejected.  
Hash/count reconciliation separately checked; passed after fixing two fixture defects discovered during verification.

**ИСТОЧНИКИ:** TECHNICAL_ARCHITECTURE §§2.4, 6.5, 12.1; 01_PROJECT_RULES; 05_DEVELOPMENT_SETUP.

**ЧТО ИЗМЕНИЛОСЬ:** Corpus and serving release composition are now machine-readable and exact. Empty draft manifest acceptance criterion is implementable without weakening promotion. Manifest hash serialization is defined deterministically.

**ЧТО ОБНОВИТЬ:** QA should record independent acceptance results in its own QA source of truth. No architecture update required unless QA identifies a conflict.

**ОТКРЫТЫЕ ВОПРОСЫ:** Executable repository validator has not yet been committed; cross-record checks are specified/documented but will be implemented in a later Stage 0 iteration. Quality contracts remain pending.

**СЛЕДУЮЩЕЕ ДЕЙСТВИЕ:** Independent QA; development proceeds next to quality contracts.
