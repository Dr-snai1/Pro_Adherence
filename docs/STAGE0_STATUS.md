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

- `model_descriptor()` direct-helper mutable revision alias rejection is now implemented and regression-tested; this hardening does not reopen QA-S0-005.
- CI currently uses `python-version: "3.13"`; patch-level drift has already occurred (3.13.15 → 3.13.16). Environment/lockfile work must pin the intended reproducible runtime policy.

## Remaining Stage 0 work

The validator/gates workstream is implemented developer-side: cross-record referential integrity and unique producers; manifest reconciliation; promotion evidence/compatibility with complete-lineage coverage; lineage reconstruction; public-boundary checks; CLI; tests; mutation audit; CI.

Independent QA of this workstream is still pending. Remaining Stage 0 acceptance areas include:

- environment / lockfile and reproducible runtime policy;
- minimal local build/materialization flow beyond validation;
- independent QA of validator/gates;
- final end-to-end Stage 0 build/validate/test acceptance.

## Developer verification — validator/gates

On implementation commit `293ef214cddb132e32b339d2baf0a4938a6e531c`, GitHub Actions run `37803936823` checked out the exact committed state and ran the full unit suite, all focused validator CLI modes, the aggregate validator and the independent semantic mutation audit. The suite passed 43 tests on Python 3.13.16 with jsonschema 4.26.0; `contracts/corpus/release/lineage/boundary/stage0` all passed; all 11 injected semantic defects failed as expected and the exact minimal-lineage chain matched.

## Promotion-quality predicate

The former architecture ambiguity is resolved in the authoritative TECHNICAL_ARCHITECTURE. Development now implements fail-closed PASS-only promotion evidence: report status must match checks; scope is direct artifact or direct run output only; each promoted artifact needs qualifying coverage; exact evidence aggregation is AND; WARN/FAIL have no waiver; rejected events never qualify for release promotion.

Developer verification is complete on final implementation commit `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`: GitHub Actions run `37813141576` / job `113434865098` succeeded on Python 3.13.16 with jsonschema 4.26.0; 68 tests passed; focused CLI and aggregate `stage0` passed; mutation audit rejected 21/21 injected defects and the separate semantic decision matrix matched 12/12 expected outcomes. The aggregate `stage0` path now includes a deterministic promoted-release smoke that executes the pass-only predicate.

Intermediate implementation commit `1a8ee69606d6640e44ff390e106ecb1d4c949a9d` is superseded by `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2` because final readback identified and closed an aggregate-acceptance coverage gap. Targeted independent QA is still pending. Stage 0 remains **OPEN / NOT RELEASE-READY**.

## Current blocking QA defects

Independent validator/gates QA registered four new defects after the earlier QA-S0-001–005 closures:

- `QA-S0-006` — promotion-quality contract: **IMPLEMENTED / TARGETED INDEPENDENT QA PENDING**. Current implementation source: `bcd6ad1b2ca7f1a2f97aabde36326edf2374c1a2`; final handoff commit: `37dfc2d52b37fd68a4dad7d28fb7e791d8615f96`.
- `QA-S0-007` — lineage DAG cycle detection: **OPEN / BLOCKING / NOT FIXED BY THE PROMOTION-QUALITY WORKSTREAM**.
- `QA-S0-008` — public/research boundary fail-closed: **OPEN / BLOCKING / NOT FIXED BY THE PROMOTION-QUALITY WORKSTREAM**.
- `QA-S0-009` — clean-checkout bare CLI/install contract: **OPEN / BLOCKING / NOT FIXED BY THE PROMOTION-QUALITY WORKSTREAM**.

The final promotion-quality diff does not add cycle detection, packaging/install metadata, or the missing `data/research` / `data/restricted` ignore rules. Therefore QA-S0-007–009 remain separate implementation work and must not be inferred closed from the 68-test promotion-quality suite.

## Historical records

Historical migration and handoff records are retained; obsolete handoffs are explicitly marked `SUPERSEDED` rather than deleted. They remain audit history and are not the current status source.

Current status is this document plus the latest QA source of truth on Google Drive.
