# Stage 1 one-source offline ingestion — provisional technical contract

> For operational Stage/QA status use Google Drive 07_STAGE_STATUS (owner 00). This candidate is not a scientific verdict, QA acceptance, or promoted public release.

Implements TECHNICAL_ARCHITECTURE section 12.2 using PubMed XML, without NCBI/ESearch/EFetch, retries, workflow_dispatch or any private evidence. Test XML contains only fabricated records. Source science Check A/B, query inclusion policy, and final PubMed search strategy are separate and not resolved here.

## Local Windows runbook

Use the repository's intended checkout and pinned C:\Pro_Adherence\python-3.13.16\python.exe (verify both exist, git rev-parse HEAD, Python version and actual module __file__ in the same Python process; historical stale-path import is documented in 00_SETUP). Commands, executed from checkout:

1. python -m pip install --no-deps -r requirements.lock
2. python -m pip install --no-deps -r requirements-stage1.lock
3. python -m pip install --no-build-isolation --no-deps -e .
4. python -m unittest discover -s tests -p 'test_stage1_*.py' -v
5. python -m pro_adherence.stage1_ingest --raw tests/fixtures/stage1_pubmed.xml --metadata tests/fixtures/stage1_pubmed_meta.json --workspace C:\Pro_Adherence\stage1-synthetic-workspace

Step 5 is synthetic-only. For existing private evidence use the audited offline pilot command below; this is NOT a scientific corpus inclusion decision. Workspace must be outside the public repository. The optional exact numpy==2.3.5 / pyarrow==26.0.0 lock is for local research only and does not change Stage 0/static serving requirements.

## Artifact behavior

- Immutable raw: raw/<SHA256>.xml (copy is byte-preserving, rejected on hash drift). Query, UTC retrieval timestamp, source cursor, access and license are explicit inputs.
- Output: snapshots/<opaque UUIDv7>/ with articles.parquet, source_records.parquet, external_ids.parquet, working.sqlite, source_provenance.json, corpus_manifest.json (status=draft), qa_report.json and checksums.json.
- Full texts are not fetched. The exact official NLM PubMedArticleSet PUBLIC DTD declaration is accepted then stripped from parser input only (never fetched, never changed in archived raw). Other DTDs and entity declarations fail closed. Article/Abstract is preferred; if absent, one English OtherAbstract is allowed as a labelled fallback with type and source provenance; foreign alternatives are not silently substituted. An unresolved MedlineDate maps to unknown publication date rather than an inferred year. Multiple AbstractText sections use newline separators. DOI is lowercase/canonicalized; original DOI and display title persist. PMID required. Two different PMIDs with the same DOI or conflicting same-PMID records fail closed. Repeated identical PMID entries are recorded and collapsed.
- Source-record Parquet entries preserve Stage 0 article_source_record schema fields exactly, with original title/DOI and repeated-source count in parsed_fields; external IDs preserve article_external_id schema shape.
- Stable source/entity IDs and snapshot identity derive from pinned rules and exact hashes. These IDs are opaque UUIDv7-format deterministic values, not chronological IDs and not cross-source resolution. Raw, normalized and canonical outputs are never copied to a public serving path.
- License metadata is project-internal/restricted and deny-all publication; no public release/promotion path exists. Manifest reuses the Stage 0 corpus-release schema field names. SQLite is only a local working index.
- Existing snapshot is reverified, not overwritten. Rebuild from identical frozen XML/metadata into separate fresh workspaces must yield identical hashes; any artifact mutation breaks readback. No private data are stored in the code repository.

## Offline import of existing private TASK-0003 samples (diagnostic only)

The corrected primary evidence package at Git commit `8209c76a550b5768875ab862f0a0d9632bf1acd7`, run `r-bdeb0005a5c3b1352fae8b9f15432ae2`, root `0739ca4dde4c4ce9fcc5aee3b8a84b9a264b296864525753056c400469d98106` contains three EFetch XML files with 100 frozen records each, not a complete PubMed literature corpus. Original D/E/PDC `only` semantics are scientifically unresolved; no precision/relevance is inferred.

Under the Windows runbook in `00_SETUP`, select the exact candidate checkout, pinned Python 3.13.16, and independently verify that `pro_adherence.stage1_private_pilot.__file__` resolves to the intended `src` (stale Python module imports were previously observed). The whole private package must already be available in local/research backup storage; discover the actual absolute path on that machine.

```powershell
$Python = 'C:\Pro_Adherence\python-3.13.16\python.exe'
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& $Python -c 'import pro_adherence.stage1_private_pilot as p; print(p.__file__)'
& $Python -m pro_adherence.stage1_private_pilot `
  --private-package 'ABSOLUTE_PATH_TO_EXISTING_PRIVATE_PACKAGE_ROOT' `
  --workspace 'C:\Pro_Adherence\stage1-frozen-sample-pilot' `
  --evidence-commit '8209c76a550b5768875ab862f0a0d9632bf1acd7' `
  --expected-package-root '0739ca4dde4c4ce9fcc5aee3b8a84b9a264b296864525753056c400469d98106'
```

The importer issues no HTTP/NCBI requests and does not dispatch workflows. It calls the complete existing `pubmed_evidence.verify(require_final=True)` before any writes, checks package root, immutable inventory, query hash, accepted EFetch timestamps and sample XML/PMID identity. Only an independent local private workspace receives immutable raw, per-branch Parquet/SQLite, draft manifests and diagnostic aggregate counts and hashes, never public serving outputs. These branches together have 300 sample positions and 299 distinct PMID across samples; this does not establish a final canonical corpus.

Actual owner-local execution and backed-up restore readback, full-scope PRE_QA and independent 04 QA remain pending. CI runs synthetic equivalents, never private data. Historic evidence stays immutable.

## Known limits / acceptance boundary

Stage 1 acceptance still requires clean-checkout end-to-end run in exact CPython 3.13.16 with pyarrow and numpy, independent schema/runtime verification, two different checks, genuine local backed-up raw evidence, a justified inclusion policy, and independent 04 QA on an atomic exact commit. Real PubMed variants (MedlineDate, revised citations, PubmedBookArticle) may need separately tested parsing support. This code intentionally fails closed on unsupported/ambiguous inputs; the synthetic fixture is not validation of scientific precision.

Neither this document nor CI changes the scientific frozen query artifacts or current Stage status.
