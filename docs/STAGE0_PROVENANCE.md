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

Cross-record uniqueness/referential-integrity checks beyond JSON Schema remain a later repository-validator responsibility.

## QA-S0-005 model identity (implemented and independently verified)

`model_identity_hash` is SHA-256 of compact UTF-8 JSON, ordered keys: `identity_schema`, `content_digest`, `identity_namespace`, `identity_key`, `immutable_revision`. Explicit nulls are required. Model display name and model ref ID are excluded. Immutable revision requires namespace and key. At least digest or revision is non-null; both included when available.

Computation digest is SHA-256 of compact UTF-8 JSON in key order `input_artifact_hashes`, `code_ref_id`, `config_hash`, `model_identity_hash`, `schema_version`. Model-backed/non-model nullability is enforced in schema and executable helper; cross-record resolution uses `src/pro_adherence/computation_signature.py`.

**Superseded / migration:** former optional `computation_signature.model_digest` is superseded by required nullable `model_identity_hash`; existing records need explicit migration and digest recomputation. QA-S0-001–005 are independently CLOSED. Stage 0 remains OPEN because validator/build/E2E acceptance work is still incomplete.


Migration details: `docs/STAGE0_MODEL_IDENTITY_MIGRATION_2026-10-08.md`.
