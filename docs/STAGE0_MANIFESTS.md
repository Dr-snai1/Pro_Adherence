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

The current authoritative contract is fail-closed and PASS-only for promotion.

For every `quality_report`, declared `status` must equal the aggregate of its checks with severity `fail > warn > pass`: any FAIL check makes the report FAIL; otherwise any WARN makes it WARN; otherwise all checks PASS and the report is PASS. An inconsistent declared report status is invalid.

For `promotion_event.decision = promoted`, `quality_report_ids` is the exact evidence set. Every referenced report must exist, be internally consistent, have `status = pass`, and apply to at least one event artifact. Artifact-scoped evidence covers only the exact `subject_artifact_id`. Run-scoped evidence covers only direct `subject_run_id -> run_output -> artifact_id` outputs; transitive or inferred coverage is invalid. Every promoted artifact requires at least one qualifying PASS report, and every report in the evidence set must be relevant to at least one event artifact.

Promotion aggregation is logical AND. WARN and FAIL do not qualify promotion and have no waiver/override in the current baseline. `compute_asset.quality_report_id` does not create implicit promotion coverage; a report counts only when explicitly listed in the event evidence set. Historical reports outside that evidence set remain provenance and do not automatically block the current decision.

A rejected promotion event never satisfies a promoted-release gate. Its referenced reports may be PASS/WARN/FAIL if internally consistent and relevant to at least one event artifact; complete per-artifact coverage is not required for rejection.

For a promoted release, every referenced promotion event must itself be promoted, target that exact release, and satisfy the promotion-quality predicate. The union of valid promotion-event artifact coverage must cover every artifact in the release manifest.

> **SUPERSEDED / historical state:** before the architecture decision of 2026-10-08, this section stated that PASS-only quality semantics were unresolved and routed the question to 02 — Техническая архитектура. That statement is retained here only as history and is not the current contract.
