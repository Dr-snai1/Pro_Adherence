# Stage 0 development status

Status date: 2026-10-08  
Overall Stage 0 status: **OPEN / NOT RELEASE-READY**

## Independently closed QA defects

Independent QA rerun on `main@c6e8d9d394fb23630b85a51691e4975d8ad46d6d` closed:

- `QA-S0-001` — provenance root `oneOf` discrimination;
- `QA-S0-002` — validating complete `lineage_bundle` fixture;
- `QA-S0-003` — versioned alias/merge/split/supersession identity history;
- `QA-S0-004` — immutable version references reject mutable aliases.

QA evidence included the committed Python regression suite (`7/7 PASS`, exit code 0) plus an independent schema/graph traversal/semantic mutation audit.

These defects are closed and must not be reopened without a new regression.

## Open blocker

`QA-S0-005` — **OPEN / BLOCKING / IMPLEMENTED AND DEVELOPER-VERIFIED; INDEPENDENT QA PENDING**.

Scope: immutable model identity in `compute_asset.computation_signature`.

Architecture has resolved the model identity rule. Targeted implementation is present and developer verification passed: GitHub Actions run 37764391921 completed successfully with 15/15 tests passing on Python 3.13.15 and jsonschema 4.26.0; a separate helper-independent SHA-256 recomputation matched the committed model and non-model fixtures. Independent QA has not closed the blocker.

## Remaining Stage 0 work

The following acceptance areas remain open because the executable repository validation/build flow has not yet been completed:

- cross-record uniqueness and referential-integrity gates;
- generic manifest hash/count reconciliation;
- promotion-evidence resolution and compatibility checks;
- executable lineage reconstruction checks;
- environment / lockfile and minimal local commands;
- final end-to-end Stage 0 build/validate/test acceptance.

## Historical records

Historical migration and handoff records are retained unchanged, including superseded records. They remain audit history and are not the current status source.

Current status is this document plus the latest QA source of truth on Google Drive.
