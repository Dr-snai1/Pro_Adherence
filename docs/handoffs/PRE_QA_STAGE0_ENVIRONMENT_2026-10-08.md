> **HISTORICAL / SUPERSEDED as active PRE_QA admission evidence.** This record documents the earlier environment/package remediation from parent `66af98ef...`. Independent admission later blocked on the lack of an exact CPython 3.13.16 runtime on the QA host. Preserve this record as history; current operational status remains only in project `07_STAGE_STATUS`.

# Stage 0 PRE_QA admission record — environment / package / clean checkout

**ОТ КОГО:** временный чат реализации Stage 0
**КОМУ:** 03 — Разработка
**ТЕМА:** reproducible environment, official package install, bare CLI, clean-checkout PRE_QA
**ТИП:** committed historical admission metadata / developer preflight record; NOT independent QA and NOT live Stage status

## КОНТЕКСТ

Exact rejected admission parent: `66af98ef102b52b73a4812e8f644ea41aaa4a161`. This record was part of descendant candidate `6d81685431b11bbf8fa4d4410fa5945921c1b49a`; it preserves the original parent provenance. The later independent PRE_QA admission did not prove an implementation defect: the QA host had CPython 3.13.5 and could not install exact 3.13.16 through the attempted host-runtime path. The portable-runtime remediation supersedes this file as active admission evidence.

Pinned requirements baseline at the time: `01_PROJECT_RULES v0.3`, `08_PRE_QA_GATE`, `TECHNICAL_ARCHITECTURE revision 22`. Current operational status is read only from `07_STAGE_STATUS`; this repository record does not duplicate or override it.

## РЕЗУЛЬТАТ / ЗАПРОС

Historical result: candidate `6d816854...` added Python 3.13.16 pinning, exact dependency/build versions, standard src-layout packaging, installed editable package validation, bare validator commands, clean-checkout CI and executable PRE_QA preflight. This was not sufficient for independent QA admission because it still assumed host availability of exact CPython 3.13.16.

## ПРОВЕРКА

Historical developer path: clean checkout → exact Python → install `requirements.lock` → `pip install --no-build-isolation --no-deps -e .` → unit suite → focused bare CLI → aggregate `stage0` → mutation audit → PRE_QA static checks. Developer CI passed; independent QA execution remained blocked by exact-runtime availability.

## ИСТОЧНИКИ

- Google Drive `01_PROJECT_RULES v0.3`.
- Google Drive `08_PRE_QA_GATE`.
- Google Drive `TECHNICAL_ARCHITECTURE revision 22`.
- Google Drive `07_STAGE_STATUS`.
- Historical candidate `6d81685431b11bbf8fa4d4410fa5945921c1b49a`.

## ЧТО ИЗМЕНИЛОСЬ

This record itself is now marked historical/superseded as active admission evidence. Its implementation history is not rewritten.

## ЧТО ОБНОВИТЬ

Use `PRE_QA_STAGE0_PORTABLE_RUNTIME_2026-10-08.md` and the final external developer handoff for the new candidate. `07_STAGE_STATUS` remains untouched by development.

## ОТКРЫТЫЕ ВОПРОСЫ

None inside this historical record. Any current blockers belong to `07_STAGE_STATUS`.

## СЛЕДУЮЩЕЕ ДЕЙСТВИЕ

Historical only; no action should be taken from this record.
