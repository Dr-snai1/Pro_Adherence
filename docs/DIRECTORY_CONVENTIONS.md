# Directory conventions

Scope: Stage 0 repository skeleton. Operational Stage/readiness/QA status is maintained only in project `07_STAGE_STATUS`.

## Tracked in Git

- `contracts/schemas/` — machine-readable schemas for IDs, entities, artifacts, runs, provenance, manifests, and quality contracts.
- `contracts/manifests/` — minimal/example manifests that are safe to version in Git.
- `contracts/policies/` — access/license and promotion policy definitions.
- `configs/` — declarative, non-secret versioned configuration.
- `src/pro_adherence/` — installed Python implementation and CLI modules.
- `scripts/` — small repository/build/preflight utilities; scientific one-off analyses do not become source of truth here.
- `tests/` — developer tests and fixtures using synthetic/public-safe data only.
- `serving/data/releases/` — explicitly promoted public static serving artifacts only.
- `web/` — future static web source; no production backend is required.
- `docs/` — implementation documentation, including the immutable runtime contract in `docs/ENVIRONMENT.md`.
- `.python-version`, `pyproject.toml`, `requirements.lock` — exact Stage 0 runtime/package/lock contract.

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

Secrets are never committed. Access/license rules are defined by Stage 0 contracts and policy; validation must enforce them rather than relying on directory names alone. PRE_QA additionally audits the tracked tree and candidate changed paths so packaging, lock, CI and documentation changes cannot carry research/restricted payloads or secret-like files.


## Stage 0 serving materialization rule

For the Stage 0 tracked tree, `serving/data/releases/.gitkeep` is the only infrastructure placeholder admitted without release evidence. Any other payload placed under `serving/data/releases/**` is rejected by the tracked-tree boundary gate. Public serving bundles are generated outputs of `pro_adherence.materialize`: every payload must be selected by a validated promoted release manifest and reconcile exact artifact identity/hash/schema/type plus access/publication permission. Extra or unselected files fail closed. This is an implementation guard for the Stage 0 skeleton, not a parallel publication contract.
