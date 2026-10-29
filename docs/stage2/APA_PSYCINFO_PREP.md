# Stage 2 · APA PsycINFO via Brunel / EBSCOhost — current acquisition prep

**STATE: SOURCE-DERIVED SEARCH CANDIDATE; LIVE APA SEARCH AND EXPORT NOT YET EXECUTED.** Stage 2 OPEN. Do not promote to a validated query or start a full export until a small live test establishes database, field behavior, record type, permitted export volume, and preserved metadata.

## Source lineage
The immutable [PubMed SELECTED v1](https://github.com/Dr-snai1/Pro_Adherence/blob/cc2fca04057dd886968c250d64283940f81a4575/configs/pubmed/medication-adherence-SELECTED.v1.json) contains the 180 original lexical expressions in six blocks with counts **2 + 54 + 15 + 69 + 36 + 4**. The new [APA candidate generator](../../scripts/stage2/apa_psycinfo_search_plan.py) imports the existing audited [WoS source-lexicon extractor](../../scripts/stage2/wos_search_plan.py); it cannot modify the frozen PubMed source. Source/payload SHA256 and the exact generated queries are included in its manifest.

**Primary lexical translation (not yet empirically validated):** for each frozen block, search its original lexicon as `(TI (term1 OR ...) OR AB (term1 OR ...))`; combine the **six** individual EBSCOhost Advanced Search history results using OR, or use the equivalent generated one-line candidate if the live UI accepts it. Verify the exact interpreted search, including quote expansion, against Search History export. **KW is not in primary.** An extra `KW` clause is generated separately for *sensitivity investigation only*. Never silently introduce APA Thesaurus headings or replace PubMed MeSH with an imagined heading. A new APA Thesaurus/controlled-vocabulary strategy or modified inclusion rule requires scientific acceptance under project contracts.

Run offline from repository root:
```powershell
py -3.13 scripts/stage2/apa_psycinfo_search_plan.py --out "$env:LOCALAPPDATA\Pro_Adherence\APA_Stage2_Temp\search_candidate"
```
The command is optional for research staff because the developer can materialize its outputs into the restricted Drive. It creates **15 files**: 6 primary block queries, 6 keyword sensitivity block queries, 2 full queries, manifest. It refuses to overwrite populated folders. No sign-in, network access or API token is used.

## Live pilot — only after institutional access
1. Start at [Brunel A–Z Databases](https://libguides.brunel.ac.uk/az/databases), select **APA PsycInfo**, and sign in using the institution-supported login. Ensure search scope is **APA PsycINFO only**, not APA PsycARTICLES/PsycTests, MEDLINE or EBSCO Discovery Service. Verify platform display (EBSCOhost) rather than assuming it based only on the library link.
2. In Advanced Search test small rare-term block `(TI (pharmacoadherence OR pharmionics) OR AB (pharmacoadherence OR pharmionics))`; verify no parser error. Then try each original six-block primary query, keep searches as separate lines, and combine them by OR through Search History; if the interface allows the single full query, verify its count against the six-OR history result. Do **not** report a hit count until the actual APA-only live UI shows one.
3. Confirm language **English** and the precise journal/article publication-type selections actually available. **Peer reviewed ≠ journal article**; do not substitute a peer-reviewed-only facet or a generic all-sources “Articles” label without field audit. Record actual facet names, time, selected database, search mode, expanders, resulting count and the full expanded query. EBSCO can export Search History including database, results, filters, expanders and interpreted query.
4. Export **a tiny sample (e.g. 10 records)** in available native citation format, preferably RIS where supported. Inspect actual first export for stable APA/EBSCO source ID (e.g. accession number), title/author/year, DOI and PMID if present, language, publication type, abstract and cited reference metadata **if present**. RIS usually does not guarantee a full cited-reference list. Record format, retention of abstracts and actual per-batch caps in the live interface.
5. Only after pilot integrity and permitted export limits are confirmed, implement/checkpoint the full APA export path using owner-authenticated UI, stage on authorized C:, upload original files plus manifest to a restricted Google Drive folder, and independently read back/verify source counts, IDs and SHA256. No licensed records in public GitHub, no scripted credentials, no speculative use of bulk-export facilities.

**Bulk export conditional:** EBSCO documents an optional `Export results (Up to 25,000)` feature requiring institution enablement, a *personal* MyEBSCO account, a short-lived emailed download link, and provider-defined usage caps. This is not proof that the Brunel account enables it, and not a reason to create accounts without the owner's choice. If absent, establish live normal export limits before writing any 500-record-batch assumptions.

## Methodological non-equivalence and science gates
- PubMed `[mh:noexp]` has no automatic APA Thesaurus equivalent.
- PubMed `[tiab:~0/1]` is not necessarily equivalent to EBSCOhost quoted exact-adjacency phrases.
- EBSCOhost unqualified keyword search may include authors and other unintended fields; use explicitly `TI` and `AB` for main translation. `KW` (and controlled `SU`) change retrieval and require separate analysis/decision.
- Source record types (article, chapter, book, dissertation, retraction) must be preserved and audited; do not infer journal-article eligibility from a proxy facet without owner-approved mapping.
- No premature PubMed+WoS two-source canonical deduplication. One consolidated three-source merge/deduplication only after APA source is archived and verified.

## References
- [Brunel A–Z APA PsycInfo](https://libguides.brunel.ac.uk/az/databases) and [Brunel EBSCOhost exports](https://www.brunel.ac.uk/life/library/SubjectSupport/EndNote-Fusion-formerly-RefWorks).
- [APA EBSCOhost quick reference guide: field codes](https://www.apa.org/pubs/databases/training/ebsco.pdf); Premji & Kraus, *Research Synthesis Methods* 2025, [translation methodology](https://pmc.ncbi.nlm.nih.gov/articles/PMC12527542/).
- [EBSCOhost Searching Tips](https://connect.ebsco.com/s/article/EBSCOhost-Searching-Tips?language=en_US).
- [EBSCO Search History export](https://connect.ebsco.com/s/article/Downloading-your-Search-History-in-the-New-EBSCO-User-Interfaces?language=en_US).
- [EBSCO conditional bulk export guidance](https://connect.ebsco.com/s/article/Exporting-up-to-25-000-Results?language=en_US).

**NEXT REQUIRED LIVE EVIDENCE:** A screenshot of the APA PsycINFO-only authenticated Advanced Search page (plus results/search-history after the small test). The owner alone authenticates; the assistant then refines and tests the supported export code against observed UI rather than predicting it.
