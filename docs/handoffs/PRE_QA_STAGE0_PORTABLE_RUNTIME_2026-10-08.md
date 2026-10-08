> **HISTORICAL / SUPERSEDED AS ACTIVE ADMISSION.** Portable-runtime design provenance retained; the consolidated TASK-0001 candidate metadata supersedes this as active developer admission evidence. Current operational status remains only in project `07_STAGE_STATUS`.\n\n# Stage 0 PRE_QA admission record — portable exact CPython 3.13.16 runtime

**ОТ КОГО:** временный чат реализации Stage 0 / PRE_QA runtime remediation
**КОМУ:** 03 — Разработка
**ТЕМА:** portable exact CPython 3.13.16 path for independent QA
**ТИП:** committed admission metadata / new atomic candidate preparation; NOT independent QA and NOT live Stage status

## КОНТЕКСТ

Independent PRE_QA for `6d81685431b11bbf8fa4d4410fa5945921c1b49a` against `TECHNICAL_ARCHITECTURE revision 22` was blocked before substantive QA because the QA host exposed CPython 3.13.5 and the attempted host-runtime installer could not supply exact CPython 3.13.16. This remediation must therefore be a new atomic descendant of exact parent `6d81685431b11bbf8fa4d4410fa5945921c1b49a`.

Pinned requirements baseline: `01_PROJECT_RULES v0.3`, `08_PRE_QA_GATE`, `05_DEVELOPMENT_SETUP`, `06_TESTING_QA_SETUP`, `TECHNICAL_ARCHITECTURE revision 22`. Operational Stage/readiness/QA status is read only from `07_STAGE_STATUS`; this record does not duplicate it.

## РЕЗУЛЬТАТ / ЗАПРОС

The candidate introduces a primary QA runtime envelope using the Docker Official Image for Python pinned as `python@sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024` on `linux/amd64`. `scripts/run_pre_qa_exact_runtime.sh` verifies `Python 3.13.16` first inside the container, verifies candidate SHA/clean tree from the read-only repository mount, installs the exact lock/package in ephemeral storage, runs unit/focused/stage0/mutation acceptance, and runs the reusable PRE_QA preflight with explicit SHA, parent and architecture revision.

For environments without Docker/Podman, `scripts/run_pre_qa_source_fallback.sh` uses official `Python-3.13.16.tar.xz`, SHA-256 `f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d`, verifies the hash before extraction, builds an isolated interpreter, creates a clean venv and executes the same acceptance flow. Build prerequisites are explicit and absence of them fails closed.

`scripts/pre_qa_gate.py` no longer hardcodes an admission parent: `--expected-parent` and `--architecture-revision` are explicit required inputs. GitHub Actions keeps the native exact-3.13.16 path and adds the pinned OCI execution path. The prior environment PRE_QA record is retained but explicitly historical/superseded as active admission evidence.

## ПРОВЕРКА

Developer check A is the native exact-runtime GitHub Actions job plus the pinned OCI job on the immutable candidate. Developer check B is separate readback: Docker Hub manifest/platform/runtime metadata; Python.org release/source SHA; Git candidate diff/parent relation; absence of tag-only acceptance identity, secret mounts and restricted paths; current-status scan; unchanged `07_STAGE_STATUS`; and Drive revision readback confirming `TECHNICAL_ARCHITECTURE revision 22`.

The final exact candidate SHA cannot be embedded in its own commit without changing that SHA. It is supplied to the scripts at execution time and must appear in the external final handoff together with CI run/job evidence and the 10/10 checklist.

## ИСТОЧНИКИ

- `01_PROJECT_RULES v0.3` → atomic exact-commit QA, double verification, single current-status source.
- `08_PRE_QA_GATE` → 10 simultaneous admission criteria.
- `05_DEVELOPMENT_SETUP` / `06_TESTING_QA_SETUP` → developer and independent-QA boundaries.
- `TECHNICAL_ARCHITECTURE revision 22` → Docker/OCI allowed for reproducibility, zero-cost static-first production unchanged.
- Docker Official Image `python` → `linux/amd64` manifest digest above and image metadata `PYTHON_VERSION=3.13.16`.
- Python.org 3.13.16 release → official XZ source identity and SHA-256 above.
- Exact parent `6d81685431b11bbf8fa4d4410fa5945921c1b49a`.

## ЧТО ИЗМЕНИЛОСЬ

Only reproducibility/preflight/package-install/CI/instructional documentation and tests needed for portable exact-runtime admission. Scientific schemas, manifests, promotion semantics, serving/publication contracts and project `07_STAGE_STATUS` are not changed.

## ЧТО ОБНОВИТЬ

After immutable commit + CI, the external handoff to 03 must record candidate SHA, parent SHA, OCI repository/digest/platform/runtime, commands and exit codes, exact test count, CI run/jobs, independent readback audit and the formal 10/10 PRE_QA checklist. 00 alone may update `07_STAGE_STATUS` after an accepted handoff.

## ОТКРЫТЫЕ ВОПРОСЫ

No new architecture question. The Python package lock remains version-pinned rather than file-hash-pinned; `docs/ENVIRONMENT.md` records the exact rationale and residual risk. If the QA environment forbids Docker/Podman and also lacks source-build prerequisites, that is a new infrastructure admission fact and must not be bypassed by substituting another Python patch version.

## СЛЕДУЮЩЕЕ ДЕЙСТВИЕ

Create one immutable descendant of `6d81685431b11bbf8fa4d4410fa5945921c1b49a`, execute native + OCI developer checks, perform the independent digest/source/runtime/Git/status/architecture audit, and issue a final handoff to 03 only at 10/10 `PRE_QA_GATE = PASS`. Do not route to 04 before that result.
