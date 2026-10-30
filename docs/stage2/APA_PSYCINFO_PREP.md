# Stage 2 · APA PsycINFO / EBSCOhost — verified source acquisition contract

**CURRENT 2026-10-30: COMPLETE ORIGINAL RIS + SEARCH HISTORY VERIFIED.** Stage 2 OPEN for one integrated PubMed V05 + WoS + APA corpus. No re-export or user login is required for accepted APA source. This file supersedes obsolete pilot procedures.

## Exact search and frozen source
- Database: APA PsycInfo only, via Brunel University / EBSCOhost Research Databases; search mode Proximity («Близость»).
- Original immutable [PubMed SELECTED](https://github.com/Dr-snai1/Pro_Adherence/blob/cc2fca04057dd886968c250d64283940f81a4575/configs/pubmed/medication-adherence-SELECTED.v1.json): 180 distinct lexical terms in 6 blocks (2 + 54 + 15 + 69 + 36 + 4); no changes.
- Actual search is full TI (all 180 original lexical terms OR) OR AB (all 180 original lexical terms OR), quoted multiword phrases. An extra KW sensitivity search exists but was NOT run as primary. [Offline deterministic generator](../../scripts/stage2/apa_psycinfo_search_plan.py), [full search document](https://docs.google.com/document/d/1jc7cSY18S-03Q5CjvUG-RR_s7gvcQvM55AXMmVvJ1zo/edit).
- Limiters English, Document Type Journal Article; no equivalence with Publication Type All Journals or Peer Reviewed toggle.
- Original [Search History CSV S8](https://drive.google.com/file/d/1seXLu8ny4hpzFyjWq2ZFx_5J762uJssL/view) on restricted Drive: timestamp 2026-10-30T20:22:07.000Z, 6,878 results, ONE APA PsycInfo database, English/Journal Article, Proximity. 23,733 bytes, SHA256 54c2f7e0395ea28649250658e839b4fa12ec94b19244ea2c0316817fb42e73a3.
- Submitted 10,874-character EBSCO string equals expanded/displayed query and deterministic frozen source TI/AB search character-for-character. No silent truncation in observed expanded query. CSV does not encode each expander checkbox state, so those off-states cannot be inferred from it.

## Immutable original corpus and verified format
- [Restricted APA original RIS](https://drive.google.com/file/d/1cY8c7K2YiP6rtKZh8dgDQtEjsCJEA0dD/view): 6,878 source records, 17,682,335 bytes SHA256 dfc9d2902459f068b5492e79d73ab57694a04647a56c2a2d7abd95e59c19a462. Source EBSCO UUID filename changed only as Drive metadata.
- [Private Drive folder](https://drive.google.com/drive/folders/1uEhBAv0biSAxviRqsdWLn2N4-TiA36mb): shared=false, no licensed records in public GitHub.
- Independent original byte readback and strict RIS parser: 6,878 TY/ER, 6,878 unique AN, AN=ID, source DB APA PsycInfo, eng/JOUR/Journal Article for all, no malformed records.
- 6,522 unique nonempty DOI; 356 DOI missing. Full title, abstract, author, journal, date and keywords coverage in all 6,878.
- Extra Retracted Article marker in 3 records, Peer-Reviewed Status-Unknown in 19; keep as original provenance and do not silently exclude.
- No cited-reference lists in this RIS (0/6,878); do not treat missing reference coverage as absence of citations, or manufacture CR.
- Original 10-record pilot compared with full RIS: 10/10 accession IDs present and 110/110 paired metadata fields match; never double-ingest sample.
- Original EBSCO Search History S8 count 6,878 equals full RIS 6,878; official count delta ZERO, so do not discard any records.
- [Full independent RIS + Search History readback report](https://docs.google.com/document/d/17dYGqhJ9y62ptoSbxeA-ej4coJecKvnair25NaI1AZk/edit).

## Reproducibility and scientific boundary
- [Offline RIS auditor](../../scripts/stage2/apa_ris_audit.py) fails closed on malformed blocks, duplicate AN, wrong source database/count; publishes metadata/digests only.
- [Offline EBSCO Search History auditor](../../scripts/stage2/apa_search_history_audit.py) checks frozen exact submitted/expanded query, APA-only source, filters, mode, count; synthetic negative tests include dropped terms and hidden expansions.
- Branch stage2/multisource-wos-ingest-20261029; [CI PASS at SHA ae5290c4d77a7e5ce378ff7dc50e93471ef399df](https://github.com/Dr-snai1/Pro_Adherence/actions/runs/41124323359).
- PubMed MeSH/noexp and tiab proximity, WoS TS and EBSCO quoted TI/AB are not automatically scientifically equivalent; controlled vocabulary expansion or altered inclusion criteria requires owner scientific decision.
- Next under [07_STAGE_STATUS](https://docs.google.com/document/d/1GhQfnsbxK8lilvpnZqWeFu99w67DwWKJmY5OTthxvhM/edit): source-specific ingestion, one full PubMed V05 + WoS + APA conservative resolution, provenance, citation/author linkage, source sensitivity and leave-one-source-out. No intermediate PubMed+WoS canonical release. Stage 2 OPEN; QA04 on integrated major milestone only.
