# Stage 0 executable validation

Status: implemented in the validator/gates workstream; independent QA pending.

Local commands (from repository root):

- PYTHONPATH=src python -m pro_adherence.validate contracts
- PYTHONPATH=src python -m pro_adherence.validate corpus contracts/manifests/empty_corpus.manifest.json
- PYTHONPATH=src python -m pro_adherence.validate lineage contracts/manifests/minimal_lineage.example.json
- PYTHONPATH=src python -m pro_adherence.validate release contracts/manifests/empty_release.manifest.json
- PYTHONPATH=src python -m pro_adherence.validate boundary
- PYTHONPATH=src python -m pro_adherence.validate stage0

Add --json before the subcommand for a machine-readable result. Any blocking validation error returns a non-zero exit code.

The validator resolves JSON Schema references from contracts/schemas only; it does not fetch schema references from the network. Corpus validation reconciles article count, IDs, input artifact hashes, policy file bytes/hashes and manifest hash. Release validation reconciles exact artifact metadata, publication permission, corpus compatibility, promotion evidence and validated complete-lineage coverage for each promoted artifact. Lineage validation enforces cross-record references, unique producing runs and a root-relevant direct-input/source-fetch/corpus chain, and exposes deterministic output-artifact lineage reconstruction.

Promotion quality-report semantics: the validator requires referenced quality reports to exist, but does not currently require quality_report.status = pass because the authoritative contract does not state that exact rule unambiguously. This is an architecture question for 02, not an implementation default.