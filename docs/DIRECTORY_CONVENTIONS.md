# Directory conventions

Status: Stage 0 skeleton.

## Tracked in Git

- `contracts/schemas/` — machine-readable schemas for IDs, entities, artifacts, runs, provenance, manifests, and quality contracts.
- `contracts/manifests/` — minimal/example manifests that are safe to version in Git.
- `contracts/policies/` — access/license and promotion policy definitions.
- `configs/` — declarative, non-secret versioned configuration.
- `src/pro_adherence/` — Python implementation and CLI modules.
- `scripts/` — small repository/build utilities; scientific one-off analyses do not become source of truth here.
- `tests/` — developer tests and fixtures using synthetic/public-safe data only.
- `serving/data/releases/` — explicitly promoted public static serving artifacts only.
- `web/` — future static web source; no production backend is required.
- `docs/` — implementation documentation.

## Local / off-repository by default

These paths are intentionally ignored by Git:

- `data/raw/` — immutable source responses and exports.
- `data/normalized/` — source-specific normalized records.
- `data/canonical/` — canonical scientific snapshots.
- `data/derived/` — embeddings, graphs, clustering and other derived scientific artifacts.
- `research/` — exploratory/research-only outputs.
- `restricted/` — restricted-license material.
- `artifacts/`, `backups/`, `local/` — local generated or recovery material.

The scientific layers RAW → NORMALIZED → CANONICAL → DERIVED are not publication layers. Public serving data must be produced only through an explicit promotion step into `serving/`.

Secrets are never committed. Access/license rules will be enforced by Stage 0 contracts and validation, not by directory names alone.
