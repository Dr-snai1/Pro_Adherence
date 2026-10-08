# Stage 0 consolidated closure candidate metadata — TASK-0001

**ОТ КОГО:** временный чат разработки TASK-0001
**КОМУ:** 03 — Разработка
**ТЕМА:** единый Stage 0 closure package для одной консолидированной независимой QA-приёмки
**ТИП:** committed candidate metadata / developer evidence scaffold; не independent QA и не источник live Stage-status

> Операционный Stage/readiness/QA-status поддерживается только в Google Drive `07_STAGE_STATUS`. Этот файл фиксирует реализацию и воспроизводимость candidate, но не закрывает QA-дефекты и не объявляет Stage закрытым.

## КОНТЕКСТ

Exact parent: `6d81685431b11bbf8fa4d4410fa5945921c1b49a`. Candidate обязан быть его единственным прямым потомком без merge-parent. Portable-runtime WIP `runtime-remediation-wip-20261008@86351d63063e00e7b1e9dfbb16c35fb9132d0060` использован только как provenance/source для перечитанной переносимой реализации; его 11-коммитная история не является QA target.

Pinned baseline на момент сборки: `01_PROJECT_RULES v0.3`, `08_PRE_QA_GATE`, `TECHNICAL_ARCHITECTURE revision 22`, `05_DEVELOPMENT_SETUP`, `06_TESTING_QA_SETUP`. Перед freeze внешняя handoff-запись обязана повторно подтвердить current architecture revision.

## РЕЗУЛЬТАТ / ЗАПРОС

Candidate реализует developer-side coverage для известных Stage 0 блокирующих классов без утверждения об их независимом закрытии:

- `QA-S0-007` lineage cycle class: global DAG validation отличает active recursion/back-edge от completed nodes; public reconstruction fail-closed для циклов.
- `QA-S0-008` public/research boundary: полный path family, secrets/key material, explicit serving placeholder rule и release-selected content materialization через существующие release/access/promotion contracts.
- `QA-S0-009` portable exact runtime: CPython 3.13.16, digest-pinned OCI `linux/amd64`, verified official-source fallback, installed src-layout package и bare CLI.
- `QA-S0-006-DOC-02` class: full tracked text status scan в bounded scope; historical records допускаются только с явным HISTORICAL/SUPERSEDED/CORRECTION marker.
- Stage 0 build/materialization/E2E: deterministic promoted fixture, exact selected payload mapping, delete/rebuild equality, minimal restore drill и independent tree/hash reconciliation.

Ни один из этих пунктов не означает independent QA closure. Финальная зарегистрированная передача должна просить 03 направить ровно один immutable candidate в 04 после `PRE_QA_GATE` 10/10.

## ПРОВЕРКА

Bounded lineage sweep: self-loop; two-node; cycle length >2; upstream/root-reachable cycle; descendant traversal cycle; valid chain; branching DAG; disconnected acyclic component; duplicate producer invariant; deterministic reconstruction; converging/diamond DAG без false positive.

Bounded boundary sweep: все `data/raw`, `data/normalized`, `data/canonical`, `data/derived`, `data/research`, `data/restricted`, `research`, `restricted`; Windows/Unix normalization; nested `.env`/secrets/key material; exact `serving/data/releases/.gitkeep` infrastructure exception; arbitrary serving payload; restricted/project-internal serving artifact; missing explicit selection; payload hash mismatch; publication/access mismatch; extra/unselected payload; valid selected public payload.

Status sweep: README; every tracked `docs/**/*.md`; nested handoffs; text manifests/configuration in `contracts/manifests` and `configs`. Live Stage/QA claims outside `07_STAGE_STATUS` fail unless the record is explicitly historical/superseded/correction evidence.

Canonical E2E: exact runtime envelope → locked package install → contracts/schema → lineage/corpus/release → promoted public materialization → repository boundary → delete output → deterministic rebuild → restore fixture → independent tree/hash reconciliation → regression and mutation audits.

## ИСТОЧНИКИ

- Google Drive `01_PROJECT_RULES v0.3` → atomic candidate, two different checks, single status source, registered handoff.
- Google Drive `TECHNICAL_ARCHITECTURE revision 22` → §§2.6, 6.2–6.5, 8.5–8.7, 9.1, 9.5–9.6, 10.1–10.5, 12.1, Appendix B.
- Google Drive `08_PRE_QA_GATE` → simultaneous 10/10 admission criteria.
- Google Drive `STAGE0_INDEPENDENT_QA_2026-10-08` → defect classes QA-S0-006-DOC-02 / 007 / 008 / 009 and missing build/E2E acceptance.
- Docker Official Image verification, 2026-10-08: `python:3.13.16-slim`, manifest digest `sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024`, OS/ARCH `linux/amd64`.
- Python.org release verification, 2026-10-08: `Python-3.13.16.tar.xz`, SHA-256 `f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d`.

## impact matrix

| Scope | Dependency changed? | Developer regression required | Prior evidence reuse |
|---|---|---|---|
| QA-S0-001–005 provenance/model identity | validator dependency changed | full suite + focused contracts/lineage/release + mutation | only after independent QA impact assessment |
| QA-S0-006 promotion-quality | validator dependency changed | PASS/WARN/FAIL/unrelated/inconsistent matrix rerun | only after independent QA impact assessment |
| QA-S0-007 lineage DAG | yes | bounded DAG sweep + mutation | no direct reuse for cycle criterion |
| QA-S0-008 boundary/public serving | yes | path/content/selection/access sweep + E2E | no direct reuse for boundary criterion |
| QA-S0-009 runtime/package | yes | clean exact-runtime bare CLI + installed package | prior WIP is provenance only |
| manifests/release contracts | semantic validator dependency changed, schemas unchanged | focused corpus/release + promoted fixture | independent impact assessment required |
| PRE_QA/runtime | yes | exact SHA/parent/revision + clean tree + OCI | no status carry-forward |
| build/materialization/restore | new Stage 0 acceptance surface | deterministic rebuild + restore + independent hash | new evidence required |

## ЧТО ИЗМЕНИЛОСЬ

Code/tests/scripts/CI/runtime docs/boundary ignore rules and developer evidence metadata required by TASK-0001. Existing schemas and `07_STAGE_STATUS` are not modified. Generated serving output is runtime evidence and is not committed as source of truth.

## ЧТО ОБНОВИТЬ

После immutable final commit внешняя зарегистрированная HOFF-запись должна добавить exact candidate SHA, CI run/job IDs, точное число tests, mutation/E2E hashes, PRE_QA 10/10 table, повторную architecture-revision readback и результаты independent readback audit. Этот committed документ не может self-embed SHA собственного commit без изменения SHA.

## ОТКРЫТЫЕ ВОПРОСЫ

Independent QA ещё должна оценить candidate и только она может закрыть соответствующие QA criteria. Source-build fallback остаётся резервным путём; основной developer/QA exact-runtime envelope — digest-pinned OCI. Минимальный restore drill относится только к Stage 0 synthetic fixture, не к будущей полной научной backup topology.

## СЛЕДУЮЩЕЕ ДЕЙСТВИЕ

На exact candidate выполнить Check A и отдельный Check B; повторно прочитать current `TECHNICAL_ARCHITECTURE`; при неизменном/доказанно no-impact baseline оформить `PRE_QA_GATE` 10/10 во внешнем зарегистрированном HOFF в 03. До этого не отправлять candidate в 04.
