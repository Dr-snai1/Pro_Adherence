# Stage 0 contracts — IDs, entities, access/license

Status: QA-S0-001–005 independently verified and CLOSED. Stage 0 remains OPEN; executable validator/gates are implemented developer-side and await independent QA.

## Internal IDs and immutable versions

Internal surrogate identifiers use canonical lowercase UUIDv7. External DOI/PMID/ORCID/ROR identifiers remain separate. `source_id` remains a stable provider key.

Exact version/revision fields now use `ids.schema.json#/$defs/immutable_version_ref`. Mutable pointers such as `latest`, `current`, `HEAD`, `main`, `master`, `tip`, `trunk`, `default`, `stable` and `newest` are invalid in these fields. Human-readable labels remain ordinary strings where no immutable reference is required.

## Entity contract and identity history

`contracts/schemas/entities.schema.json` defines the canonical entity records from TECHNICAL_ARCHITECTURE §§3.2–3.6 and now adds versioned `identity_resolution_event` records for `article`, `author` and `affiliation`.

Events explicitly represent `alias`, `merge`, `split` and `supersession`; they retain predecessor ID(s), successor ID(s), immutable resolution version, method, reason, evidence/provenance and timestamp. `identity_resolution_history_bundle` provides a validating example container.

The legacy `article.superseded_by` field is retained and marked deprecated. It remains a one-to-one compatibility shortcut; complete history uses `identity_resolution_event.successor_ids` and is never silently rewritten or deleted.

## Access / license

The access classes remain `public`, `project-internal`, `restricted-license`, `secret`. Publication permissions remain explicit and fail closed.

## Artifact / run / provenance

All root provenance records carry an explicit `record_type` discriminator, so `run_input` and `run_output` are machine-distinct under root `oneOf`. A validating `lineage_bundle` contract contains artifacts, producing runs, run bindings, code/config/model/environment refs, source fetches and corpus references.

## Corpus / release manifests

Corpus schema/resolver versions and release artifact schema versions use immutable-version references. Release assembly therefore cannot express mutable aliases such as `latest` in exact-version fields.

The empty draft fixtures remain valid. Hash/count reconciliation and cross-record referential integrity are now executable repository-validator responsibilities implemented in `src/pro_adherence/validate.py`.

See `docs/STAGE0_CONTRACT_MIGRATION_2026-10-08.md` for migration semantics.

## Executable validator additions

`contracts/schemas/policy.schema.json` brings the committed access-license and corpus inclusion/exclusion policy documents into the Draft 2020-12 schema gate. The validator additionally enforces cross-record references, unique immutable-output producers, manifest reconciliation, promotion evidence/compatibility and public-repository boundaries without changing the underlying QA-S0-001–005 contracts.
