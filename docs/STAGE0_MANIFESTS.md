# Stage 0 corpus and serving release manifests

Status: QA-S0-004 independently verified and CLOSED. Stage 0 overall remains OPEN; executable validator/build/E2E gates are still pending.

## Corpus release

`contracts/schemas/corpus-release.schema.json` fixes the exact corpus snapshot. `canonical_schema_version` and `entity_resolution_version` are now immutable version references rather than arbitrary non-empty strings.

## Public serving release

`contracts/schemas/release-manifest.schema.json` fixes serving artifacts by exact artifact ID, content hash, immutable schema version, role and public path. Mutable aliases such as `latest`, `current` or `HEAD` are schema-invalid in exact version fields.

Access/license and publication-permission gates are unchanged.

## Hash semantics

`manifest_hash` remains the SHA-256 of the payload excluding `manifest_hash`, serialized as UTF-8 JSON with lexicographically sorted object keys, no insignificant whitespace, separators `,` and `:`, and declared array order preserved.

The executable repository validator will continue to own hash/count reconciliation and referential integrity; this defect-fix changes only version-reference shape constraints.
