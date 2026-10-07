# Stage 0 corpus and serving release manifests

Status: implemented, developer-checked; independent QA pending.

## Corpus release

`contracts/schemas/corpus-release.schema.json` fixes the exact scientific corpus snapshot:

- exact `canonical_article_ids`;
- canonical schema and entity-resolution versions;
- explicit inclusion/exclusion policy refs with content hashes;
- exact input artifact IDs and hashes;
- `article_count`;
- manifest hash and lifecycle status.

A corpus release is therefore not a mutable database state. Once frozen, correction requires a new release; supersession is explicit.

## Public serving release

`contracts/schemas/release-manifest.schema.json` fixes a compatible serving set by exact artifact ID, content hash, schema version, role and public path. It never selects "latest" artifacts.

Every public release artifact carries access/license metadata and a publication-permission basis. The schema requires `access_class = public` and an explicit `allow` permission for the type being published.

A `draft` release may be empty. A `promoted` release must name a corpus release, contain at least one exact artifact, and cite at least one promotion event. This permits the Stage 0 empty-manifest acceptance test without weakening the promotion gate.

## Hash semantics

`manifest_hash` is the SHA-256 of the canonical serialized manifest payload **excluding the `manifest_hash` field itself**. The executable validator will enforce this rule and cross-field invariants such as `article_count == len(canonical_article_ids)`.

The JSON Schemas intentionally handle record shape; repository validation handles referential integrity and hash/count reconciliation.
