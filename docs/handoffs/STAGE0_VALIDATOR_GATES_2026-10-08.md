> **SUPERSEDED** — this intermediate handoff predates complete-lineage promotion hardening and expanded CLI/reference regression coverage. Current handoff: `docs/handoffs/STAGE0_VALIDATOR_GATES_FINAL_2026-10-08.md`.

# Stage 0 validator/gates implementation handoff — 2026-10-08

ОТ КОГО: **временный чат реализации Stage 0**  
КОМУ: **03 — Разработка**  
ТЕМА: **Pro_Adherence — executable cross-record validator / gates / lineage / promotion**  
ТИП: **implementation result / QA handoff request**

## КОНТЕКСТ

Repository: `Dr-snai1/Pro_Adherence`  
Baseline: `main@feaec13035d5d833b4746ea55a025a5c495ef92b`  
Implementation commit: `f133d660e5b07d5f6576d62004e80dac71f07989`

At task start QA-S0-001–005 were independently CLOSED and Stage 0 was OPEN / NOT RELEASE-READY. This workstream covered validator/gates + manifests + lineage + promotion and did not expand the environment/lockfile workstream.

## РЕЗУЛЬТАТ / ЗАПРОС

Implemented an executable local/static Stage 0 validator suitable for GitHub Actions:

- Draft 2020-12 schema validation with repository-local cross-file refs;
- schema validation for schemas, manifests, provenance/lineage, entity fixtures, compute fixtures and policy documents;
- cross-record referential integrity for runs, artifacts, code/config/model/environment refs, source fetches and declared corpus refs;
- unique-producing-run invariant for immutable output artifacts;
- deterministic `output artifact id -> lineage` reconstruction;
- corpus article-count/ID/input-artifact/policy/hash reconciliation;
- release exact-artifact metadata/hash/schema/type resolution, access/publication gate, corpus compatibility, promotion evidence/target/coverage and unique producing-run lineage;
- direct `model_descriptor()` hardening against mutable revision aliases;
- repository/public-boundary gate based on tracked paths, not keyword search;
- CLI modes `contracts`, `corpus`, `release`, `lineage`, `boundary`, `stage0`, plus `--json`;
- CI execution of committed tests, aggregate validator and independent semantic mutation audit.

No rule was invented for `quality_report.status = pass`; referenced quality reports must exist, but pass-only promotion semantics remain an architecture question.

**Stage 0 remains OPEN / NOT RELEASE-READY.** Request independent QA of the validator/gates implementation.

## ПРОВЕРКА

### A — committed executable suite

Verified GitHub state: `f133d660e5b07d5f6576d62004e80dac71f07989`  
CI run: `37802827745` — **success**  
CI job: `113399210631` — **success**  
Runtime: Python `3.13.16`  
Dependency: `jsonschema 4.26.0`

Commands:

```bash
python -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src python -m pro_adherence.validate stage0
PYTHONPATH=src python scripts/stage0_mutation_audit.py
```

Result:
- 37 tests run, 37 passed, exit 0;
- aggregate Stage 0 validator: PASS, exit 0;
- existing QA-S0-001–005 regression tests remain passing.

### B — independent semantic mutation audit

A separate program mutates valid fixtures rather than rerunning the unit suite. All 10 required mutations produced expected FAIL:

1. dangling ref;
2. duplicate producer;
3. wrong manifest hash;
4. wrong policy hash;
5. wrong article count;
6. wrong artifact hash;
7. promotion without evidence;
8. wrong promotion target;
9. restricted public artifact;
10. corpus mismatch.

Exact lineage traversal on the valid minimal fixture matched the expected chain: root output, unique producing run, direct input, raw/source ancestor, source fetch, corpus release, code ref, config ref, model ref and environment ref.

Additional readback/diff audit:
- final implementation files reread from GitHub;
- baseline→implementation diff inspected;
- earlier over-compression of Stage 0 docs was detected during readback and corrected before this handoff;
- no unrelated deletions remain;
- direct recursive repository-tree audit found no tracked forbidden raw/normalized/canonical/derived/research/restricted or `.env` paths.

## ИСТОЧНИКИ

Authoritative project sources:
- `01_PROJECT_RULES`;
- `TECHNICAL_ARCHITECTURE §§6.2–6.5, 7.1–7.3, 9.1, 9.5–9.6, 12.1, Appendix B`;
- `05_DEVELOPMENT_SETUP`;
- `06_TESTING_QA_SETUP`;
- `STAGE0_INDEPENDENT_QA_2026-10-08`;
- repository `docs/STAGE0_STATUS.md`;
- Stage 0 schemas/manifests/provenance docs, tests and CI workflow.

Baseline evidence source: `main@feaec13035d5d833b4746ea55a025a5c495ef92b`.

## ЧТО ИЗМЕНИЛОСЬ

Implementation changes relative to baseline:

1. `.github/workflows/stage0-tests.yml`
2. `README.md`
3. `contracts/schemas/policy.schema.json` — new
4. `docs/STAGE0_CONTRACTS.md`
5. `docs/STAGE0_MANIFESTS.md`
6. `docs/STAGE0_PROVENANCE.md`
7. `docs/STAGE0_STATUS.md`
8. `docs/STAGE0_VALIDATION.md` — new
9. `scripts/stage0_mutation_audit.py` — new
10. `src/pro_adherence/__init__.py` — new
11. `src/pro_adherence/computation_signature.py`
12. `src/pro_adherence/validate.py` — new
13. `tests/test_stage0_validator.py` — new

This handoff record itself is the additional final-history file:
`docs/handoffs/STAGE0_VALIDATOR_GATES_2026-10-08.md`.

No historical handoff was rewritten or deleted.

## ЧТО ОБНОВИТЬ

03 — Разработка:
- accept/record this implementation handoff;
- route the promotion-quality semantic ambiguity to 02 — Техническая архитектура;
- after 02 decides, update validator/tests/docs only if a pass-only quality-report rule is explicitly adopted;
- keep environment/lockfile and local build/materialization as separate remaining Stage 0 workstreams.

04 — Тестирование / QA:
- independently verify validator/gates against the authoritative contracts;
- do not treat developer tests or this handoff as QA evidence;
- retain Stage 0 as OPEN until all remaining acceptance workstreams pass.

## ОТКРЫТЫЕ ВОПРОСЫ

**Architecture:** Is `quality_report.status = pass` mandatory for every quality report referenced by a promoted release/promotion event? Current authoritative contracts require promotion evidence but do not state this exact predicate unambiguously. Implementation intentionally does not infer it.

**Remaining non-blocking implementation risks / deferred work:**
- CI Python is still `3.13` rather than patch-pinned; environment/lockfile work remains open.
- `jsonschema.RefResolver` emits a deprecation warning; migration to the `referencing` API is future hardening, not a current validation failure.
- aggregate `stage0` validates the committed empty/draft fixtures; promoted-release cases are exercised by tests/mutation audit, while a true build/materialization E2E remains a later Stage 0 workstream.

## СЛЕДУЮЩЕЕ ДЕЙСТВИЕ

1. 03 records this result.
2. 02 resolves the quality-report promotion semantic.
3. 04 performs independent QA of validator/gates.
4. Development continues environment/lockfile + minimal build/materialization.
5. Only after those workstreams: final Stage 0 E2E acceptance.

**Do not declare Stage 0 PASS from this handoff.**

## Commit metadata

Implementation commit: `f133d660e5b07d5f6576d62004e80dac71f07989`  
Final handoff commit SHA: **the Git commit containing this file; exact SHA is returned with the handoff message because a commit cannot contain its own SHA without changing it.**
