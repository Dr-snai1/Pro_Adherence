# Stage 0 executable validation

Status: validator/gates independent QA has already been executed. Overall validator/gates verdict remains FAIL / NOT ACCEPTED because QA-S0-006–009 were registered as blocking defects. QA-S0-006 executable semantics passed; only its documentation-consistency closure is in targeted reacceptance. QA-S0-007–009 remain OPEN / BLOCKING.

Local commands (from repository root):

- PYTHONPATH=src python -m pro_adherence.validate contracts
- PYTHONPATH=src python -m pro_adherence.validate corpus contracts/manifests/empty_corpus.manifest.json
- PYTHONPATH=src python -m pro_adherence.validate lineage contracts/manifests/minimal_lineage.example.json
- PYTHONPATH=src python -m pro_adherence.validate release contracts/manifests/empty_release.manifest.json
- PYTHONPATH=src python -m pro_adherence.validate boundary
- PYTHONPATH=src python -m pro_adherence.validate stage0

Add --json before the subcommand for a machine-readable result. Any blocking validation error returns a non-zero exit code. The aggregate `stage0` command also runs a deterministic promoted-release smoke fixture through the same pass-only promotion-quality predicate, so aggregate validation exercises the promotion gate rather than validating only a draft release.

The validator resolves JSON Schema references from contracts/schemas only; it does not fetch schema references from the network. Corpus validation reconciles article count, IDs, input artifact hashes, policy file bytes/hashes and manifest hash. Release validation reconciles exact artifact metadata, publication permission, corpus compatibility, promotion evidence and validated complete-lineage coverage for each promoted artifact. Lineage validation enforces cross-record references, unique producing runs and a root-relevant direct-input/source-fetch/corpus chain, and exposes deterministic output-artifact lineage reconstruction.

Promotion quality-report semantics are executable and fail closed. For every quality report used as evidence, declared status must equal the aggregate of its checks with severity fail > warn > pass. A promoted event uses exactly its quality_report_ids: every referenced report must exist, be internally consistent, have status=pass, and apply to at least one event artifact. Artifact scope covers only the identical artifact; run scope covers only direct run_output artifacts. Every promoted artifact requires at least one qualifying PASS report, so aggregation is logical AND and WARN/FAIL have no waiver or override.

Rejected events may reference internally consistent PASS/WARN/FAIL reports and do not require complete per-artifact QA coverage, but every referenced report must still apply to at least one event artifact; rejected events never qualify for a promoted release. Unreferenced historical reports and compute_asset.quality_report_id do not create implicit promotion coverage.

For a promoted release, supply the exact corpus, a semantically valid lineage bundle for every promoted root artifact, and referenced promotion/quality evidence, for example:

```bash
PYTHONPATH=src python -m pro_adherence.validate release release.json \
  --corpus corpus.json \
  --lineage lineage.json \
  --evidence quality-report.json \
  --evidence promotion-event.json
```

`--lineage` inputs are validated as complete lineage bundles, not accepted as mere record catalogs. A promoted artifact must be the root output of a validated bundle. Non-empty corpus manifests reconcile their declared input artifacts against the supplied evidence artifact catalog.
