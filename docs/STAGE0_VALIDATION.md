# Stage 0 executable validation

> **Operational status:** see project `07_STAGE_STATUS` (00 — Штаб). Historical QA evidence is retained in handoff records; this page defines executable validation semantics.

## Preferred clean-room acceptance

Independent QA should use the immutable OCI runtime described in `docs/ENVIRONMENT.md`:

```bash
bash scripts/run_pre_qa_exact_runtime.sh \
  --expected-sha <EXACT_CANDIDATE_SHA> \
  --expected-parent <EXACT_PARENT_SHA> \
  --architecture-revision 22
```

If Docker/Podman is unavailable but compiler/build prerequisites exist, use `scripts/run_pre_qa_source_fallback.sh` with the same arguments. Neither path requires host `PYTHONPATH`; the OCI path does not require host Python 3.13.16.

## Focused validation commands

After installing the exact Python 3.13.16 environment/package from `docs/ENVIRONMENT.md`, run from repository root:

- `python -m pro_adherence.validate contracts`
- `python -m pro_adherence.validate corpus contracts/manifests/empty_corpus.manifest.json`
- `python -m pro_adherence.validate lineage contracts/manifests/minimal_lineage.example.json`
- `python -m pro_adherence.validate release contracts/manifests/empty_release.manifest.json`
- `python -m pro_adherence.validate boundary`
- `python -m pro_adherence.validate stage0`
- `python scripts/stage0_mutation_audit.py`

Add `--json` before validator subcommands for machine-readable output. Any blocking validation error returns non-zero. The aggregate `stage0` command exercises deterministic promoted-release smoke through the same pass-only promotion-quality predicate rather than validating only a draft release.

The validator resolves JSON Schema references only from `contracts/schemas`. Corpus validation reconciles article count, IDs, input artifact hashes, policy bytes/hashes and manifest hash. Release validation reconciles exact artifact metadata, publication permission, corpus compatibility, promotion evidence and validated complete-lineage coverage. Lineage validation enforces cross-record references, unique producing runs and a root-relevant direct-input/source-fetch/corpus chain.

Promotion quality-report semantics remain fail-closed: a promoted event uses exactly its `quality_report_ids`; all referenced reports must exist, be internally consistent and PASS, apply to an event artifact, and collectively cover every promoted artifact by artifact scope or direct run-output scope. WARN/FAIL do not qualify and have no waiver/override in the current baseline.

## PRE_QA developer preflight

The reusable preflight now requires explicit identity inputs:

```bash
env -u PYTHONPATH python scripts/pre_qa_gate.py \
  --expected-sha <EXACT_CANDIDATE_SHA> \
  --expected-parent <EXACT_PARENT_SHA> \
  --architecture-revision 22
```

It verifies exact runtime/lock/package installation, `HEAD`, `HEAD^`, clean tree, changed-path/public-boundary rules, architecture/admission metadata, stale status/handoff markers, then orchestrates the full unit/focused/stage0/mutation gate. Formal `PRE_QA_GATE = PASS` is declared only after both developer execution and an independent readback audit satisfy all 10 criteria from project `08_PRE_QA_GATE`.


## Deterministic materialization, restore and closure audit

The canonical Stage 0 build/restore acceptance is:

```bash
env -u PYTHONPATH python scripts/stage0_e2e.py
```

It uses the committed `tests/fixtures/stage0_materialization/fixture_spec.json` and payload seed to produce a valid PASS-only promoted release, then validates lineage/corpus/release evidence and calls the installed materializer. The output contains the canonical release manifest, only selected public payloads and deterministic materialization metadata. The command deletes and rebuilds the output, compares payload and bundle tree hashes, restores the frozen synthetic input snapshot in a clean temporary location and reconciles the restored output with an independent tree/hash calculation.

The fail-closed materializer CLI is `python -m pro_adherence.materialize --release ... --corpus ... --lineage ... --evidence ... --artifact-source ARTIFACT_ID=PATH --output ...`. Exact ID/hash/schema/type/access/publication/promotion/lineage constraints are inherited from the release contracts; source mapping additionally rejects missing or extra/unselected payloads and unsafe serving paths.

The existing promotion/provenance mutation audit remains `python scripts/stage0_mutation_audit.py`. TASK-0001 adds `python scripts/stage0_closure_mutation_audit.py` for distinct lineage-cycle, boundary, status and serving-selection mutations. Full `PRE_QA` runs both audits and the E2E after the unit/focused validation suite.
