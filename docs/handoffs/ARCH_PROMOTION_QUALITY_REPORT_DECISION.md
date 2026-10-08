> **SUPERSEDED — 2026-10-08.** The requested architecture decision has been made in the authoritative TECHNICAL_ARCHITECTURE: promotion is fail-closed PASS-only with exact evidence, direct scope, mandatory per-artifact coverage, AND aggregation, no WARN/FAIL waiver, and rejected events excluded from release promotion. Historical request retained below.

# Handoff — promotion quality-report semantics architecture decision

**ОТ КОГО:** 03 — Разработка  
**КОМУ:** 02 — Техническая архитектура  
**ТЕМА:** Pro_Adherence — Stage 0 promotion gate / quality_report status semantics  
**ТИП:** architecture decision request

**КОНТЕКСТ:**  
Stage 0 validator/gates are implemented. Current provenance contract defines `quality_report.status` as `pass|warn|fail`; `promotion_event` requires non-empty `quality_report_ids` and a `decision` of `promoted|rejected`. Current TECHNICAL_ARCHITECTURE requires QA evidence, promotion gate, lineage/license/reproducibility, but does not unambiguously state which quality-report statuses qualify for promotion.

Implementation therefore checks referenced quality-report existence but intentionally does not infer `status = pass`.

**РЕЗУЛЬТАТ / ЗАПРОС:**  
Define the normative promotion predicate for referenced quality reports.

At minimum decide:
1. Is every quality report referenced by a `promotion_event(decision=promoted)` required to have `status=pass`?
2. If `warn` may be allowed, what explicit rule/override evidence makes promotion valid?
3. Is `fail` always promotion-blocking?
4. Must each referenced quality report be scoped directly to a promoted artifact (`subject_artifact_id`) or may run-scoped evidence (`subject_run_id`) qualify? If run-scoped evidence qualifies, define the required relation from that run to each promoted artifact.
5. Must every promoted artifact be covered by at least one qualifying quality report, or is event-level/shared evidence sufficient?
6. If several quality reports cover the same artifact/run, define aggregation semantics (e.g. any fail blocks; all pass; warn policy).

The rule must be machine-enforceable without relying on human interpretation.

**ПРОВЕРКА:**  
Source → current TECHNICAL_ARCHITECTURE + provenance schema.  
Method → normative cross-check against implemented validator and promotion contract.  
Result → evidence existence is specified; exact status/coverage predicate is not.  
Interpretation → pass-only or warn-override behavior would be a new architecture rule and cannot be invented by 03.

**ИСТОЧНИКИ:**  
`TECHNICAL_ARCHITECTURE §§1.1–1.2, 2.6, 6.2, 6.5, 9.1, 9.5–9.6, Appendix B`; `01_PROJECT_RULES`; `05_DEVELOPMENT_SETUP`; `06_TESTING_QA_SETUP`; `contracts/schemas/provenance.schema.json`; validator implementation commit `293ef214cddb132e32b339d2baf0a4938a6e531c`.

**ЧТО ИЗМЕНИЛОСЬ:**  
No architecture rule has been changed by development. Current validator deliberately stops at evidence existence/target/coverage and complete lineage.

**ЧТО ОБНОВИТЬ:**  
If 02 adopts a rule, update TECHNICAL_ARCHITECTURE explicitly and preserve superseded wording/version transition if needed. Return an implementation contract to 03 covering schema/validator/tests/docs changes.

**ОТКРЫТЫЕ ВОПРОСЫ:**  
The six status/coverage questions above. No other validator architecture conflict is currently known.

**СЛЕДУЮЩЕЕ ДЕЙСТВИЕ:**  
02 makes the exact promotion-quality decision, performs consistency checks across promotion/provenance/QA sections, and returns mandatory handoff to 03. Until then, pass-only semantics must not be implemented by assumption.
