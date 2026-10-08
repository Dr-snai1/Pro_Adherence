# Stage 0 provenance contract

Status: QA-S0-001, QA-S0-002 and QA-S0-005 independently verified and CLOSED. Stage 0 overall remains OPEN / NOT RELEASE-READY.

Root provenance records retain required record_type discriminators. lineage_bundle remains the validating container for artifacts, runs, bindings, code/config/model/environment refs and source fetches.

src/pro_adherence/validate.py now enforces cross-record references, declared corpus references, source-fetch/raw-artifact linkage and the invariant that an immutable output has at most one producing run. It also reconstructs a deterministic chain from output artifact ID to producing run, exact inputs, source artifacts/fetches, corpus IDs and code/config/model/environment refs, with parent/child artifact results.

QA-S0-005 model identity remains model_identity_hash over the canonical immutable descriptor. The direct helper is additionally hardened to reject mutable revision aliases even when called without prior JSON Schema validation.

Promotion evidence and release compatibility are executable validator concerns; no research run is promoted merely because it exists. Serving selection is controlled by an explicit release manifest.