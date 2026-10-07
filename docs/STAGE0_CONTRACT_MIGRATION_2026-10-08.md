# Stage 0 contract migration — 2026-10-08

Status: current migration note for QA-S0-001–004.

## Provenance root records

**Before:** root provenance records had no discriminator; `run_input` and `run_output` were structurally identical and therefore invalid under root `oneOf`.

**Now:** every root provenance record requires `record_type` equal to its contract name. Existing serialized provenance records must add this field. No existing record class was deleted.

The previous composite `minimal_lineage.example.json` is superseded by a validating `lineage_bundle` fixture. It now carries complete minimum lineage components needed for reconstruction.

## Canonical identity resolution

A new `identity_resolution_event` contract records alias/merge/split/supersession history for article, author and affiliation IDs. Old IDs remain represented as `predecessor_ids`; successor ID(s), resolution version, method/reason and evidence are retained.

`article.superseded_by` is **deprecated, not removed**. It remains valid for legacy one-to-one references but is superseded for complete history by identity-resolution events.

## Immutable version references

`version_ref` now delegates to `immutable_version_ref`. Exact schema/resolver/adapter/model-revision fields likewise use that contract. Mutable aliases are invalid. Existing immutable literal versions remain valid.

This is a deliberate tightening of fields that architecture defines as exact version references; human-readable labels elsewhere are unchanged.

## Out of scope

QA-S0-005 is unchanged and remains owned by the separate architecture decision.
