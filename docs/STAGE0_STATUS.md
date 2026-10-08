# Stage 0 development status

Status date: 2026-10-08  
Overall Stage 0 status: **OPEN / NOT RELEASE-READY**

## Independently closed QA defects

Independent QA has now closed all five known blocking defects:

- `QA-S0-001` — provenance root `oneOf` discrimination;
- `QA-S0-002` — validating complete `lineage_bundle` fixture;
- `QA-S0-003` — versioned alias/merge/split/supersession identity history;
- `QA-S0-004` — immutable version references reject mutable aliases;
- `QA-S0-005` — immutable model identity in `compute_asset.computation_signature`.

`QA-S0-001–004` were independently closed on the earlier regression rerun. `QA-S0-005` was independently closed on `main@3b0bcf77eea6274b82c98f3ab8011f58569d67d6`.

For QA-S0-005, independent QA executed the committed full suite on Python 3.13.16 with jsonschema 4.26.0: 15 tests, OK, 0 failures/errors. Independent helper-free SHA-256 recomputation matched the committed model identity and model/non-model computation digests, and the 33-file tree restoration was verified blob-for-blob.

All known blocking defects QA-S0-001–005 are CLOSED and must not be reopened without a new regression.

## Non-blocking hardening

- `model_descriptor()` currently assumes schema-valid `model_ref`; direct helper use should also reject mutable revision aliases. This is a future validator hardening item and does not reopen QA-S0-005.
- CI currently uses `python-version: "3.13"`; patch-level drift has already occurred (3.13.15 → 3.13.16). Environment/lockfile work must pin the intended reproducible runtime policy.

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
