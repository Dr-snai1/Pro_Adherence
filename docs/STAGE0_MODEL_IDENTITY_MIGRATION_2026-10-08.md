# Stage 0 model identity migration — 2026-10-08

> **HISTORICAL / SUPERSEDED as live status.** Migration evidence retained for QA-S0-005. Operational Stage/readiness/QA status is maintained only in project `07_STAGE_STATUS`.

## Superseded contract

The previous active field `computation_signature.model_digest` is **superseded**. It must not be silently accepted as the current computation-signature model component.

The current field is required and nullable:

`computation_signature.model_identity_hash`

Existing serialized computation signatures that use `model_digest` require explicit migration and recomputation.

## Canonical model identity

For a model-backed computation:

`model_identity_hash = SHA-256(canonical_model_identity_descriptor)`

The descriptor has exactly these ordered fields:

1. `identity_schema` = `"model-identity/v1"`
2. `content_digest`
3. `identity_namespace`
4. `identity_key`
5. `immutable_revision`

Null values are serialized explicitly. `model_name` and `model_ref_id` are excluded from the descriptor.

At least one of `content_digest` or `immutable_revision` must be non-null. A non-null immutable revision requires non-null `identity_namespace` and `identity_key`.

## Computation signature migration

For model-backed computation:

- `model_ref_id != null`;
- `model_identity_hash != null`;
- the hash must equal the canonical hash of the resolved `model_ref`.

For non-model computation:

- `model_ref_id = null`;
- `model_identity_hash = null`.

After migration, recompute the full computation-signature digest over the canonical ordered fields:

`input_artifact_hashes`, `code_ref_id`, `config_hash`, `model_identity_hash`, `schema_version`.

## Historical compatibility

Historical records remain auditable; this migration does not rewrite or delete them. The superseded `model_digest` semantics remain documented for history but are not part of the active contract.
