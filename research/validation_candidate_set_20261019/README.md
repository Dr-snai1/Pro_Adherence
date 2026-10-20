# Provisional PubMed evaluation cohort (2026-10-19)
**NOT a validated gold standard.** Contains 500 auto-screened R and 500 auto-screened N,
with PubMed PMIDs, title, source, and label provenance. Label confidence and rule provenance are explicit.
This is a deliberately balanced challenge set and MUST NOT be used to estimate
prevalence, overall PubMed retrieval precision, or external recall.

- R = evidence in title+abstract consistent with actual patient medication-taking adherence,
  persistence or refill/coverage outcome; includes historical examples.
- N = provisionally classified as other-topic or lacking substantive patient medication adherence evidence; 129 included lower-confidence negative examples REQUIRE independent expert review before any gold-standard use.
- U = ambiguous/missing abstract; kept in unresolved_candidates.csv and not forced N.
- Existing user labels from the 150-sheet are preserved and marked human-confirmed;
  earlier assistant-read positives are *not* independently human-confirmed.
- Query provenance in manifest.json; original V04_S0 config has not been changed.
- Audit of *silver label noise* and expert dual review are mandatory before release gate.
- Full copyrighted abstracts are deliberately NOT redistributed in GitHub; obtain them from PubMed by PMID when reviewing.
- Candidate set selection is biased toward clear labels; test sensitivity on held-out
  documented clinical benchmark separately, not just on these generated rows.

## Reference v1.1 retention guarantee
All 21 earlier assistant-reviewed positive examples are present as R (one user-confirmed); all 12 earlier user-reviewed N examples are present as N. This is NOT independent expert consensus. See manifest.json and label_basis for provenance. The accepted PubMed search query is unchanged.

## Current evaluation reference: FINAL v2 (2026-10-20)
Primary active set is `reference_FINAL_v2_R500_N369.csv`, with exactly 500 R
and 369 N (869 unique PMIDs). Removed the 129 less-confident negatives,
plus two further incorrect/at-risk N (24702721, 33464991). Prior 1000-row
file remains as historical superseded evidence, NEVER use it as active set.
All 21 assistant-reviewed R and 12 user-reviewed N examples are retained.
Final means fixed operational selection; heuristically screened references
are NOT independently adjudicated gold labels. See v2 manifest.

## PMID-by-PMID query comparison, 2026-10-20

Based on the fixed 500 R / 369 N active silver reference, not population inference.
Verified live PubMed ESearch using two differently partitioned sets of exact PMID constraints and an independent export recount. The baseline selected query is unchanged.

| Query | TP / 500 R | FN / 500 R | FP / 369 N | TN / 369 N | Sensitivity | Specificity |
|---|---:|---:|---:|---:|---:|---:|
| V04_S0 | 499 | 1 | 312 | 57 | 99.80% | 15.45% |
| V04_S0 + methods v2 | 500 | 0 | 324 | 45 | 100.00% | 12.20% |

Record-level checks: `reference_FINAL_v2_query_2x2.csv`; query and evidence hashes: `reference_FINAL_v2_query_2x2.json`. This retrospective corpus is assembled from related queries and has imperfect heuristic labels. Its sensitivity/specificity numbers are **within-reference diagnostic rates, not externally validated retrieval characteristics**.

## V05 phrase search: independently verified PubMed 2×2 (2026-10-20)

Compared exactly as written in the user-provided Google Drive file `PubMed_V05_PHRASE_CANDIDATE_20261020.txt`, using the **same frozen 500 R / 369 N silver reference** as V04. Full NCBI ESearch reports 49,930 articles and no phrase warnings. Two independent PMID partition strategies produced identical matching sets; exported CSV recount passed.

| Query | TP / 500 R | FN / 500 R | FP / 369 N | TN / 369 N | Sensitivity | Specificity |
|---|---:|---:|---:|---:|---:|---:|
| V04_S0 | 499 | 1 | 312 | 57 | 99.80% | 15.45% |
| V04_S0 + methods v2 | 500 | 0 | 324 | 45 | 100.00% | 12.20% |
| V05 phrase candidate | 496 | 4 | 96 | 273 | 99.20% | 73.98% |

V05 misses 4 previously retrieved R PMIDs (12441805, 23225173, 28807035, 37091492) and newly retrieves PMID 38289464, whose R labeling requires caution: its abstract/title may pertain to CGM-device rather than medication-taking adherence. The count-based values are fixed-test-set *silver metrics*, not external sensitivity/specificity estimates. The selected production PubMed query on main is unchanged.

Audit: `reference_FINAL_v2_V05_PHRASE_2x2.csv` (869 PMID rows), `reference_FINAL_v2_V05_PHRASE_2x2.json` (hashes, live source, second-pass checks), `research/PubMed_V05_PHRASE_CANDIDATE_20261020.txt` (source query snapshot). Older query and reference versions remain preserved for provenance.
