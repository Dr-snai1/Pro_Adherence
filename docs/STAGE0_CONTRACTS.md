# Stage 0 contracts — IDs, entities, access/license

Status: QA-S0-001–005 independently verified and CLOSED. Stage 0 remains OPEN; executable validator/gates are implemented developer-side and await independent QA.

Internal IDs remain canonical lowercase UUIDv7; exact versions use immutable_version_ref and reject mutable aliases. Entity identity history, access/license metadata, provenance record discriminators and model identity semantics are unchanged by this workstream.

Policy documents now have contracts/schemas/policy.schema.json so repository policy fixtures participate in the Draft 2020-12 schema gate. Cross-record behavior that JSON Schema cannot express is enforced by src/pro_adherence/validate.py.

Corpus and release manifests retain their existing schemas and hash semantics. The validator now owns executable hash/count reconciliation, artifact resolution, promotion evidence, compatibility and repository boundary checks.