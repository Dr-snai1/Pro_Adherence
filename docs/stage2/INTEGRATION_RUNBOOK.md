# Stage 2 — offline three-source integration runbook

This is an **execution contract**, not an additional Stage/status document. Current approval and project status remain solely in restricted Google Drive \`07_STAGE_STATUS\`. Scientific decisions remain in \`02_SCIENTIFIC_GUIDANCE\`; technical architecture in \`TECHNICAL_ARCHITECTURE\` §12.3.

## Inputs (immutable, source-specific)

- PubMed V05 accepted private archive: three 7z transport chunks + JSON manifest. Verify each chunk and concatenated SHA-256, extract using a 7-Zip CLI that supports V05's header encryption, and verify the accepted 753-file snapshot using \`scripts/v05/run_portable.py --verify-only\`. **Do not** rerun PubMed ESearch/EFetch. Use extracted \`stage1-v05-private/<run_id>/raw/\` with exactly 250 \`000001.xml\` … \`000250.xml\` files. The source must yield 49,998 distinct PMID, including 49,912 journal-family and 86 book-family items.
- WoS Core Collection: original 000001–000500 TXT SHA-256 \`3247ec52dabe2ab3a156df6b57bfdd38b4e0496861458e70d0de0f5fe59ce020\`; original 501–30,635 ZIP SHA-256 \`513e5837858801f72bc4063ca03cb482223b4b07a569276e1a1796cc1286d6bf\`; 30,635 unique UT; 413 preserved NR/CR source mismatches.
- APA PsycINFO: original 6,878-record RIS SHA-256 \`dfc9d2902459f068b5492e79d73ab57694a04647a56c2a2d7abd95e59c19a462\`; 6,878 unique AN; three Retracted Article flags; no cited-reference lists in this export.

Original exports remain private; no licensed/raw data are committed to this public repository. The three search strategies are not presumed scientifically equivalent.

## Execution

The following command is for reproducibility in an authorized **private offline** environment with adequate temporary storage. It is not evidence that the full run has occurred:

\`\`\`bash
PYTHONPATH=src python scripts/stage2/run_three_source.py \
  --pubmed-raw-dir /private/accepted-v05/stage1-v05-private/RUN/raw \
  --wos-first /private/original-wos-000001-000500.txt \
  --wos-zip /private/original-wos-501-30635.zip \
  --apa-ris /private/original-apa-6878.ris \
  --out /private/NEW-EMPTY-stage2-candidate
\`\`\`

\`load_sources\` fails closed on frozen WoS/APA hashes, ZIP integrity, file count, unique source IDs, PubMed record-family counts, APA retraction count and WoS NR/CR anomaly count. \`reconcile_sources\` uses indexed DOI/PMID matching, vetoes conflicting identifiers, duplicate-source and book/journal key ambiguities, and never uses fuzzy title/author matching. The full result includes source-specific records, source-to-canonical links, identity decisions, author/affiliation observations (not disambiguated persons or institutions), citation resolution and original reference coverage flags. Absence of APA references is **unknown coverage**, not zero citations. Every row includes raw-source provenance.

There is **one** private three-source candidate (\`three_source.json.gz\`). Three \`loo_*.json.gz\` files are sensitivity-only recomputations with one source omitted; none is a separate accepted two-source canonical release. All gzip timestamps and JSON key ordering are deterministic. A manifest records file hashes and counts. No publication/promotion or Stage transition is performed.

## Verification and current limits

For scientific/technical acceptance, check **both** (1) independent census/lineage and original source file checksums, including exact UID/UT/AN coverage, family/retraction/NR-CR flags and ambiguous identity decisions; and (2) deterministic full rerun, bytewise SHA-256 of emitted artifacts, substantive spot checks of identifier/citation matches and Git CI on a pinned commit. Then save the **private** candidate in the existing restricted project Google Drive location and read it back by exact Drive IDs/hashes. Only a major integrated candidate proceeds to QA04, followed by the owner's Stage decision.

The initial implementation and its synthetic tests do **not** establish a completed full three-source run or any accepted canonical publication count. The current assistant execution container can verify V05 transport SHA-256 but cannot extract its encrypted-header 7z with installed libarchive; a compatible 7-Zip CLI is required before attempting that full run. This is an execution environment limitation, not a source-data defect. No new source retrieval or PubMed rebuild is authorized.
