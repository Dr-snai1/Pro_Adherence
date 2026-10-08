# Stage 0 corpus and serving release manifests

Status: QA-S0-004 independently verified and CLOSED. Stage 0 overall remains OPEN; executable manifest validator/gates are implemented developer-side and await independent QA.

## Corpus release

`contracts/schemas/corpus-release.schema.json` fixes the exact corpus snapshot. `canonical_schema_version` and `entity_resolution_version` are now immutable version references rather than arbitrary non-empty strings.

## Public serving release

`contracts/schemas/release-manifest.schema.json` fixes serving artifacts by exact artifact ID, content hash, immutable schema version, role and public path. Mutable aliases such as `latest`, `current` or `HEAD` are schema-invalid in exact version fields.

Access/license and publication-permission gates are unchanged.

## Hash semantics

`manifest_hash` remains the SHA-256 of the payload excluding `manifest_hash`, serialized as UTF-8 JSON with lexicographically sorted object keys, no insignificant whitespace, separators `,` and `:`, and declared array order preserved.

The executable repository validator now owns hash/count reconciliation and referential integrity. Corpus validation checks article count/ID uniqueness, exact input-artifact hashes, policy bytes/hashes and `manifest_hash`. Release validation checks exact catalog metadata, access/publication permission, corpus compatibility, promotion-event resolution/target/coverage, referenced quality-report existence and unique producing-run lineage for promoted artifacts.

## Promotion-quality boundary

The authoritative contracts do not yet state unambiguously that every referenced `quality_report` must have `status = pass`. The validator therefore requires referenced reports to exist but does not invent a pass-only promotion rule; this exact semantic question is routed to `02 — Техническая архитектура`.
