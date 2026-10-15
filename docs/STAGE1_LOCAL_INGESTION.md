# Stage 1 one-source offline ingestion — provisional technical contract

> For operational Stage/QA status use Google Drive 07_STAGE_STATUS (owner 00). This candidate is not a scientific verdict, QA acceptance, or promoted public release.

Implements TECHNICAL_ARCHITECTURE section 12.2 using PubMed XML, without NCBI/ESearch/EFetch, retries, workflow_dispatch or any private evidence. Test XML contains only fabricated records. Source science Check A/B, query inclusion policy, and final PubMed search strategy are separate and not resolved here.

## Local Windows runbook

Use the repository's intended checkout and pinned C:\Pro_Adherence\python-3.13.16\python.exe (verify both exist, git rev-parse HEAD, Python version and actual module __file__ in the same Python process; historical stale-path import is documented in 00_SETUP). Commands, executed from checkout:

1. python -m pip install --no-deps -r requirements.lock
2. python -m pip install --no-deps -r requirements-stage1.lock
3. python -m pip install --no-build-isolation --no-deps -e .
4. python -m unittest discover -s tests -p test_stage1_ingest.py -v
5. python -m pro_adherence.stage1_ingest --raw tests/fixtures/stage1_pubmed.xml --metadata tests/fixtures/stage1_pubmed_meta.json --workspace C:\Pro_Adherence\stage1-synthetic-workspace

Do not execute step 5 with real research data until its source/provenance/access policy is approved. Workspace must be outside the public repository. The optional exact numpy==2.3.5 / pyarrow==26.0.0 lock is for local research only and does not change Stage 0/static serving requirements.

## Artifact behavior

- Immutable raw: raw/<SHA256>.xml (copy is byte-preserving, rejected on hash drift). Query, UTC retrieval timestamp, source cursor, access and license are explicit inputs.
- Output: snapshots/<opaque UUIDv7>/ with articles.parquet, source_records.parquet, external_ids.parquet, working.sqlite, source_provenance.json, corpus_manifest.json (status=draft), qa_report.json and checksums.json.
- ISBN/full text are not fetched; title/abstract only when provided. DOI is lowercase/canonicalized; original DOI and display title persist. PMID required. Two different PMIDs with the same DOI or conflicting same-PMID records fail closed. Repeated identical PMID entries are recorded and collapsed.
- Source-record Parquet entries preserve Stage 0 article_source_record schema fields exactly, with original title/DOI and repeated-source count in parsed_fields; external IDs preserve article_external_id schema shape.
- Stable source/entity IDs and snapshot identity derive from pinned rules and exact hashes. These IDs are opaque UUIDv7-format deterministic values, not chronological IDs and not cross-source resolution. Raw, normalized and canonical outputs are never copied to a public serving path.
- License metadata is project-internal/restricted and deny-all publication; no public release/promotion path exists. Manifest reuses the Stage 0 corpus-release schema field names. SQLite is only a local working index.
- Existing snapshot is reverified, not overwritten. Rebuild from identical frozen XML/metadata into separate fresh workspaces must yield identical hashes; any artifact mutation breaks readback. No private data are stored in the code repository.

## Known limits / acceptance boundary

Stage 1 acceptance still requires clean-checkout end-to-end run in exact CPython 3.13.16 with pyarrow and numpy, independent schema/runtime verification, two different checks, genuine local backed-up raw evidence, a justified inclusion policy, and independent 04 QA on an atomic exact commit. Real PubMed variants (MedlineDate, revised citations, PubmedBookArticle) may need separately tested parsing support. This code intentionally fails closed on unsupported/ambiguous inputs; the synthetic fixture is not validation of scientific precision.

Neither this document nor CI changes the scientific frozen query artifacts or current Stage status.
