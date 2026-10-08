# Handoff — QA-S0-006 documentation-only closure rerun request

ОТ КОГО: **03 — Разработка**  
КОМУ: **04 — Тестирование / QA**  
ТЕМА: **Pro_Adherence — QA-S0-006-DOC-01 documentation consistency rerun**  
ТИП: **narrow QA rerun request / documentation-only defect repair**

## КОНТЕКСТ

Workflow authority: `01_PROJECT_RULES v0.2`, rule 13 (atomic change before QA).

The earlier multi-commit repair history remains audit provenance, but under v0.2 it is **not** the QA target. QA must inspect one exact atomic candidate commit containing the complete repository state: unchanged executable implementation + tests + repaired current documentation + supersession records + this self-check/routing record. The exact candidate SHA cannot be embedded in the file that creates that SHA; it is supplied in the chat handoff from 03 to 04 and QA must check that exact commit only.


Independent targeted QA confirmed that executable QA-S0-006 promotion-quality semantics PASS on implementation commit:

`bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`

but kept QA-S0-006 OPEN because current `docs/STAGE0_MANIFESTS.md` still described the former unresolved-quality state.

QA requested a documentation-only repair without changing promotion-quality code/schema/tests unless necessary.

## РЕЗУЛЬТАТ / ЗАПРОС

The stale current documentation has been repaired.

Historical component commits (audit provenance only, **not separate QA targets**):

- documentation repair: `600b435e17543374e54d8ed284b1551a1bc822f4`;
- historical supersession/readback cleanup: `116742ced6c72e12e9db7b8435faa6153bca0b82`;
- earlier routing record: `d1f3a426d66b3568588a684acf54d3b4c2298f8e`.

Under `01_PROJECT_RULES v0.2 §13`, the QA target is the single exact atomic candidate commit supplied by 03 in the chat handoff. That commit contains the cumulative state of these changes and the unchanged executable implementation.

Please perform the narrow QA rerun requested by QA-S0-006-DOC-01 on that one exact commit:

1. confirm code/schema/fixtures/tests/workflow semantics are unchanged from `bcd6ad1...`;
2. read back corrected `docs/STAGE0_MANIFESTS.md`;
3. verify current docs agree with the authoritative PASS-only promotion contract;
4. search for stale unresolved-quality claims in current normative docs;
5. verify historical stale records are explicitly marked SUPERSEDED rather than silently rewritten/deleted.

If these checks pass, QA-S0-006 may be closed.

QA-S0-007–009 remain OPEN / BLOCKING and are outside this rerun.

## DOCUMENTATION REPAIR

`docs/STAGE0_MANIFESTS.md` now states the current contract:

- report status aggregate is `fail > warn > pass`;
- promoted evidence is PASS-only;
- WARN and FAIL do not qualify and have no waiver/override;
- `quality_report_ids` is the exact evidence set;
- artifact scope is exact artifact only;
- run scope is direct `subject_run_id -> run_output -> artifact_id` only;
- transitive/inferred coverage is invalid;
- each promoted artifact requires at least one applicable PASS report;
- unrelated evidence is invalid;
- `compute_asset.quality_report_id` creates no implicit promotion evidence;
- rejected events never qualify release promotion;
- promoted-release event union must cover every release artifact.

The former unresolved-quality wording is retained only as an explicit **SUPERSEDED / historical state** note.

## HANDOFF CORRECTION / HISTORY

The historical implementation handoff `docs/handoffs/STAGE0_PROMOTION_QUALITY_FINAL_2026-10-08.md` now carries an explicit correction: its executable evidence remains valid, but its former claim of complete documentation consistency is superseded by QA-S0-006-DOC-01 and the subsequent documentation repair.

The older validator/gates handoff `docs/handoffs/STAGE0_VALIDATOR_GATES_FINAL_2026-10-08.md`, which still contains the old unresolved architecture question in its historical body, is explicitly marked **SUPERSEDED** at the top.

The already-executed targeted request `docs/handoffs/QA_STAGE0_PROMOTION_QUALITY_REQUEST.md` is also marked **SUPERSEDED** and points to this documentation closure step.

No historical record was deleted.

## CHANGED FILES FOR QA-S0-006-DOC-01 REPAIR

Documentation repair/supersession changed only:

- `docs/STAGE0_MANIFESTS.md`
- `docs/STAGE0_STATUS.md`
- `docs/handoffs/STAGE0_PROMOTION_QUALITY_FINAL_2026-10-08.md`
- `docs/handoffs/QA_STAGE0_PROMOTION_QUALITY_REQUEST.md`
- `docs/handoffs/STAGE0_VALIDATOR_GATES_FINAL_2026-10-08.md`

No promotion-quality implementation code, schema, fixture, test, mutation-audit script, or workflow was modified by this documentation repair.

## ПРОВЕРКА

Developer/readback verification for the atomic candidate tree:

Requirements/architecture links:
- `01_PROJECT_RULES v0.2 §13`;
- current `TECHNICAL_ARCHITECTURE §§2.6, 6.2, 6.5, 9.1, 9.5–9.6, Appendix B`.

Self-check evidence:

Source → Git comparison from executable implementation `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2` to the atomic QA candidate tree.

Method → exact GitHub compare + direct readback/search of current docs.

Result:

- all post-implementation changes are documentation files only;
- no code/schema/test/fixture/workflow path changed;
- current normative docs no longer state that promotion-quality status semantics are unresolved;
- stale unresolved text remains only inside explicitly SUPERSEDED historical handoffs or explicit historical notes;
- QA-S0-007–009 remain explicitly OPEN / BLOCKING;
- Stage 0 remains OPEN / NOT RELEASE-READY.

Interpretation → QA-S0-006 executable evidence is unchanged; the requested blocking documentation inconsistency has been repaired without semantic implementation changes.

## ИСТОЧНИКИ

- current `TECHNICAL_ARCHITECTURE §§2.6, 6.2, 6.5, 9.1, 9.5–9.6, Appendix B`;
- independent QA-S0-006 targeted verdict;
- executable implementation `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`;
- `docs/STAGE0_MANIFESTS.md`;
- `docs/STAGE0_PROVENANCE.md`;
- `docs/STAGE0_VALIDATION.md`;
- `docs/STAGE0_STATUS.md`;
- historical handoffs listed above.

## ЧТО ИЗМЕНИЛОСЬ

Only documentation consistency and supersession metadata.

Promotion-quality executable semantics remain exactly those already independently tested PASS by 04.

## ЧТО ОБНОВИТЬ

04 should update the defect register after the narrow documentation/current-main rerun.

If PASS:

`QA-S0-006 = PASS — CLOSED`

Do not change:

- `QA-S0-007 = OPEN / BLOCKING`
- `QA-S0-008 = OPEN / BLOCKING`
- `QA-S0-009 = OPEN / BLOCKING`

Do not declare Stage 0 PASS.

## ОТКРЫТЫЕ ВОПРОСЫ

None for QA-S0-006.

Separate blockers remain QA-S0-007–009 plus broader environment/lockfile, build/materialization/rebuild/restore and final E2E work.

## СЛЕДУЮЩЕЕ ДЕЙСТВИЕ

04 checks only the exact atomic candidate commit supplied in the chat handoff. If documentation consistency and supersession checks pass while implementation identity remains unchanged, close QA-S0-006 and return the verdict to 03. Because QA-S0-007–009 remain blocking in Stage 0, no later Stage may begin.

Stage 0 remains **OPEN / NOT RELEASE-READY**.
