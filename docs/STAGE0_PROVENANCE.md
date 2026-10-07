# Stage 0 provenance contract

Status: QA-S0-001 and QA-S0-002 fixed in implementation; independent QA rerun pending.

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

## Explicitly unchanged

QA-S0-005 is not addressed here. The rule that connects model identity to `compute_asset.computation_signature` still requires the separate architecture decision and must not be inferred from this defect-fix.
