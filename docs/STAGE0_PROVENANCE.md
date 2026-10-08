# Stage 0 provenance contract

Status: QA-S0-001, QA-S0-002 and QA-S0-005 independently verified and CLOSED. Stage 0 overall remains OPEN / NOT RELEASE-READY.

## Root record discriminator

Every root provenance record has required `record_type` with a schema-level `const`. This makes record types machine-unique under the root `oneOf`; specifically, a valid `run_input` no longer also validates as `run_output`, and vice versa.

## Complete lineage bundle

`lineage_bundle` is a first-class root contract. It requires:

- root output artifact ID and corpus release ID(s);
- input/output artifacts;
- producing run(s);
- `run_input` and `run_output`;
- code/config/environment refs;
- an explicit model-ref collection (empty only when no model applies);
- source-fetch linkage.

`contracts/manifests/minimal_lineage.example.json` is a model-backed example containing a raw source artifact, canonical input artifact, output artifact, producing run, both run bindings, code/config/model/environment refs, source fetch and corpus linkage.

## Reproducibility boundaries

Schema, adapter and model revision fields that are immutable references use the shared immutable-version contract. Code refs remain Git commit SHAs; configs and lockfiles remain content-addressed.

Cross-record uniqueness/referential-integrity checks beyond JSON Schema are enforced by `src/pro_adherence/validate.py`, including run/artifact/ref/source-fetch/corpus resolution and the invariant that an immutable output has at most one producing run.

## QA-S0-005 model identity (implemented and independently verified)

`model_identity_hash` is SHA-256 of compact UTF-8 JSON, ordered keys: `identity_schema`, `content_digest`, `identity_namespace`, `identity_key`, `immutable_revision`. Explicit nulls are required. Model display name and model ref ID are excluded. Immutable revision requires namespace and key. At least digest or revision is non-null; both included when available.

Computation digest is SHA-256 of compact UTF-8 JSON in key order `input_artifact_hashes`, `code_ref_id`, `config_hash`, `model_identity_hash`, `schema_version`. Model-backed/non-model nullability is enforced in schema and executable helper; cross-record resolution uses `src/pro_adherence/computation_signature.py`.

**Superseded / migration:** former optional `computation_signature.model_digest` is superseded by required nullable `model_identity_hash`; existing records need explicit migration and digest recomputation. QA-S0-001–005 are independently CLOSED. Stage 0 remains OPEN because validator/build/E2E acceptance work is still incomplete.


Migration details: `docs/STAGE0_MODEL_IDENTITY_MIGRATION_2026-10-08.md`.

## Executable lineage and hardening

The validator reconstructs deterministic lineage from an output artifact ID to its unique producing run, exact input/ancestor artifacts, source fetches, corpus release IDs, code/config/model/environment refs and parent/child artifact results. The direct `model_descriptor()` helper now also rejects the mutable revision aliases forbidden by `immutable_version_ref`, even when helper callers bypass JSON Schema validation.

Promotion evidence and serving compatibility are checked against exact release-manifest references; existence of a research run alone is never promotion evidence.

For promotion, a release artifact must be the root output of a semantically valid `lineage_bundle`; a standalone `run_output`/producer reference is not sufficient evidence of complete lineage.

A semantically valid root lineage must reconstruct at least one direct input artifact, one relevant source fetch and one relevant corpus release; unrelated records elsewhere in the bundle do not satisfy those requirements.

## Promotion-quality evidence

The promotion-quality contract is now executable. `quality_report.status` must equal the `fail > warn > pass` aggregate of checks. `promotion_event.quality_report_ids` is the exact evidence set: promoted events require every referenced report to be internally consistent PASS evidence and applicable by direct artifact scope or direct `subject_run_id -> run_output -> artifact_id` scope. Every promoted artifact requires at least one qualifying report; unrelated reports, WARN, FAIL, PASS+WARN, PASS+FAIL, transitive descendants and implicit `compute_asset.quality_report_id` coverage fail closed.

Rejected events remain provenance-only: internally consistent PASS/WARN/FAIL evidence is allowed, each referenced report must be relevant to at least one event artifact, complete per-artifact coverage is not required, and the event never satisfies a promoted release gate.
