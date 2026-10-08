# Stage 0 PRE_QA admission record — environment / package / clean checkout

**ОТ КОГО:** временный чат реализации Stage 0
**КОМУ:** 03 — Разработка
**ТЕМА:** reproducible environment, official package install, bare CLI, clean-checkout PRE_QA
**ТИП:** committed admission metadata / developer preflight record; NOT independent QA and NOT live Stage status

## КОНТЕКСТ

Exact rejected admission parent: `66af98ef102b52b73a4812e8f644ea41aaa4a161`. This record is part of the new descendant candidate and preserves the parent provenance. The exact final candidate SHA cannot be embedded in its own commit without changing that SHA; it is therefore supplied as the required runtime argument to `scripts/pre_qa_gate.py` and reported in the final external developer handoff after immutable commit + CI readback.

Pinned requirements baseline: `01_PROJECT_RULES v0.3`, `08_PRE_QA_GATE`, `TECHNICAL_ARCHITECTURE revision 22`. Current operational status is read only from `07_STAGE_STATUS`; this repository record must not duplicate or override it.

## РЕЗУЛЬТАТ / ЗАПРОС

The candidate adds Python 3.13.16 pinning, an exact dependency/build lock, standard src-layout packaging, an installed editable package path for repository validation, bare validator commands, a clean-checkout CI path, and an executable PRE_QA preflight. Request to 03 after final CI: verify all 10 `08_PRE_QA_GATE` criteria and route one exact candidate to 04 only if the formal result is `PRE_QA_GATE = PASS`.

## ПРОВЕРКА

Machine-checkable developer path: clean checkout → exact Python → install `requirements.lock` → `pip install --no-build-isolation --no-deps -e .` → unit suite → focused bare CLI → aggregate `stage0` → mutation audit → PRE_QA static checks. A second audit must independently read back Git tree/diff, runtime/lock/docs/CI, status markers, changed-path boundary, parent provenance and Drive architecture revision 22. GitHub CI does not read private Drive.

## ИСТОЧНИКИ

- Google Drive `01_PROJECT_RULES v0.3` → direct readback → §§13–16 require atomic exact-commit QA, a single status source, PRE_QA admission and architecture freeze → this candidate is tied to one SHA + revision 22.
- Google Drive `08_PRE_QA_GATE` → direct readback → 10 simultaneous PASS criteria → script evidence alone is necessary but not sufficient for the formal handoff.
- Google Drive `TECHNICAL_ARCHITECTURE revision 22` → revision API/readback → pinned immutable architecture baseline exists → CI stores the revision as committed admission metadata rather than attempting private Drive access.
- Google Drive `07_STAGE_STATUS` → direct readback → current Stage/blockers belong only there → repo docs carry instructions/history, not a parallel current status.

## ЧТО ИЗМЕНИЛОСЬ

Environment/package/lock/preflight/CI/instructional documentation and explicit historical markers only. No scientific contract, schema, manifest, validator promotion semantics or `07_STAGE_STATUS` is changed by this workstream.

## ЧТО ОБНОВИТЬ

Final external handoff must add the immutable candidate SHA, CI run/job IDs, exact test count, focused/aggregate/mutation/preflight exit results and the 10/10 PRE_QA checklist. 00 may later update `07_STAGE_STATUS` only after an accepted handoff.

## ОТКРЫТЫЕ ВОПРОСЫ

Known substantive blockers in `07_STAGE_STATUS`, including QA-S0-007 and QA-S0-008, are not declared closed here. Packaging implements the developer-side bare CLI condition associated with QA-S0-009, but only independent QA may close that defect.

## СЛЕДУЮЩЕЕ ДЕЙСТВИЕ

Create one immutable descendant commit from the exact parent, run exact-SHA CI, perform the independent preflight audit, and only at 10/10 criteria issue the final developer handoff to 03 with `PRE_QA_GATE = PASS`. Do not send anything to 04 before that formal handoff.
