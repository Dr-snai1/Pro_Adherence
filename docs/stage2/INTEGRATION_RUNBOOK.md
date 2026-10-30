# Stage 2 — offline three-source integration runbook

This is an **execution contract**, not an additional Stage/status document. Current approval and project status remain solely in restricted Google Drive \`07_STAGE_STATUS\`. Scientific decisions remain in \`02_SCIENTIFIC_GUIDANCE\`; technical architecture in \`TECHNICAL_ARCHITECTURE\` §12.3.

## Inputs (immutable, source-specific)

- PubMed V05 accepted private archive: three 7z transport chunks + JSON manifest. Verify each chunk and concatenated SHA-256, extract using a 7-Zip CLI that supports V05's header encryption, and verify the accepted 753-file snapshot using \`scripts/v05/run_portable.py --verify-only\`. **Do not** rerun PubMed ESearch/EFetch. Use extracted \`stage1-v05-private/<run_id>/raw/\` with exactly 250 \`000001.xml\` … \`000250.xml\` files, plus the accepted source \`pmids/SELECTED/union.txt\` from \`research-backup/pubmed/TASK-0003/v05-proven-dp/<run_id>/\` (SHA-256 \`bbb34a0b69872c235d897d844b0338be4aa06adf167e090ae73e0d7e3ddcfe2b\`). The source must yield 49,998 distinct PMID, including 49,912 journal-family and 86 book-family items.
- WoS Core Collection: original 000001–000500 TXT SHA-256 \`3247ec52dabe2ab3a156df6b57bfdd38b4e0496861458e70d0de0f5fe59ce020\`; original 501–30,635 ZIP SHA-256 \`513e5837858801f72bc4063ca03cb482223b4b07a569276e1a1796cc1286d6bf\`; 30,635 unique UT; 413 preserved NR/CR source mismatches.
- APA PsycINFO: original 6,878-record RIS SHA-256 \`dfc9d2902459f068b5492e79d73ab57694a04647a56c2a2d7abd95e59c19a462\`; 6,878 unique AN; three Retracted Article flags; no cited-reference lists in this export.

Original exports remain private; no licensed/raw data are committed to this public repository. The three search strategies are not presumed scientifically equivalent.

## Execution

The following command is the pinned private replay interface in an authorized offline environment. The sample `/private/...` paths are temporary extraction locations, **not owner Windows paths**. The owner's C: directory is not an authoritative source and must never be required; the originals are in restricted Google Drive. The launcher is NOT itself proof of a completed durable delivery:

\`\`\`bash
PYTHONPATH=src python scripts/stage2/run_three_source.py \
  --pubmed-raw-dir /private/accepted-v05/stage1-v05-private/RUN/raw \
  --pubmed-uid-file /private/accepted-v05/research-backup/pubmed/TASK-0003/v05-proven-dp/RUN/pmids/SELECTED/union.txt \
  --wos-first /private/original-wos-000001-000500.txt \
  --wos-zip /private/original-wos-501-30635.zip \
  --apa-ris /private/original-apa-6878.ris \
  --out /private/NEW-EMPTY-stage2-candidate
\`\`\`

\`load_sources\` fails closed on frozen WoS/APA hashes, ZIP integrity, file count, unique source IDs, PubMed record-family counts, APA retraction count and WoS NR/CR anomaly count. \`reconcile_sources\` uses indexed DOI/PMID matching, vetoes conflicting identifiers, duplicate-source and book/journal key ambiguities, and never uses fuzzy title/author matching. The full result includes source-specific records, source-to-canonical links, identity decisions, author/affiliation observations (not disambiguated persons or institutions), citation resolution and original reference coverage flags. Absence of APA references is **unknown coverage**, not zero citations. Every row includes raw-source provenance.

There is **one** private three-source candidate (\`three_source.json.gz\`). Three \`loo_*.json.gz\` files are sensitivity-only recomputations with one source omitted; none is a separate accepted two-source canonical release. All gzip timestamps and JSON key ordering are deterministic. A manifest records file hashes and counts. No publication/promotion or Stage transition is performed.

## Verification and current limits

For scientific/technical acceptance, check **both** (1) independent census/lineage and original source file checksums, including exact UID/UT/AN coverage, family/retraction/NR-CR flags and ambiguous identity decisions; and (2) deterministic full rerun, bytewise SHA-256 of emitted artifacts, substantive spot checks of identifier/citation matches and Git CI on a pinned commit. Then save the **private** candidate in the existing restricted project Google Drive location and read it back by exact Drive IDs/hashes. Only a major integrated candidate proceeds to QA04, followed by the owner's Stage decision.

**Actual sandbox compute (2026-10-31, provisional):** the original accepted private V05 7z header was recovered with a temporary AES/LZMA decoder (the installed libarchive itself does not support encrypted 7z). All 1,311 original file CRCs were checked, all 250 original XMLs were recovered, 49,998 PMID and frozen UID SHA verified, with zero PubMed calls and no owner PC/USB access. One real 87,511-source-record three-source exact-ID reconciliation yielded **57,293** groups and **2,437,863** citation observations. A separately implemented identity reconstruction reproduced all **57,293 exact group-membership hashes**; a six-file compressed JSONL sandbox snapshot passed source-count and two-sided gzip SHA readback. Leave-one-source-out counts: exclude PubMed **32,226** groups; WoS **50,914**; APA **56,600**. These are provisional diagnostic counts, not accepted Stage 2 results, and no full real-data execution of this repository's monolithic `run_three_source.py` output path is claimed.

**Critical delivery blocker:** the six **private** output files exist only in the transient compute sandbox; the connected Google Drive upload action requires a connector `file_uri` that has not been made available for these generated sandbox files. No Drive upload/readback or QA04 happened. See the [private Drive evidence report](https://docs.google.com/document/d/1mEQxm8lZWATjhdyYAYIfKsWbPq0kqCBEhCZuXovbqhY/edit) with verified hashes and explicit limitation. Do not confuse that report with the private dataset. Stage2 remains OPEN; PR remains draft. Avoid all user requests to find historic C: workspaces; only the existing restricted Drive frozen originals are authoritative. No new source retrieval or PubMed rebuild is authorized.
