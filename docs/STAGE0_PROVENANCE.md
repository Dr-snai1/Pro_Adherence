# Stage 0 provenance contract

Status: implemented, developer-checked; independent QA pending.

## What is represented

`contracts/schemas/provenance.schema.json` implements the minimum provenance catalog required by TECHNICAL_ARCHITECTURE:

- immutable `artifact`;
- `run`;
- normalized `run_input` and `run_output` bindings;
- `code_ref`, `config_ref`, optional `model_ref`, and `environment_ref`;
- `source_fetch`;
- `quality_report`;
- `promotion_event`;
- `supersession_relation`;
- the architecture-level `compute_asset` contract;
- a typed `lineage_query_result`.

## Lineage rule

A scientific output is not defined by a filename or by "latest". Its producing run is linked through `run_output`; that run is linked to exact input artifacts through `run_input`, and to code/config/model/environment refs by immutable identifiers.

A valid lineage implementation must additionally enforce the relational invariant that each immutable output artifact has at most one producing run. JSON Schema defines the records; repository validation will enforce cross-record uniqueness/referential integrity.

## Content addressing / invalidation

`computation_signature` records the components mandated by TECHNICAL_ARCHITECTURE §6.3: input artifact hashes, code ref, config hash, optional model digest, and schema version, with a SHA-256 digest for the resulting signature.

Dirty state is therefore determined by dependency IDs/signatures, not by file names or modification times.

## Reproducibility boundaries

- Code refs use Git commit SHA.
- Config refs are content-addressed by SHA-256.
- Models require an immutable revision or digest, not a mutable name alone.
- Environments require a lockfile URI and hash.
- Seed policy is explicit, including `not-applicable`.
- Artifacts are immutable by contract; replacement is represented by a supersession relation.

This contract does not yet define corpus/release manifests or the executable repository validator; those are subsequent Stage 0 iterations.
