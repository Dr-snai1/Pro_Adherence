# Provisional PubMed evaluation cohort (2026-10-19)
**NOT a validated gold standard.** Contains 500 auto-screened R and 500 auto-screened N,
with PubMed PMIDs, title, source, and label provenance. Label confidence and rule provenance are explicit.
This is a deliberately balanced challenge set and MUST NOT be used to estimate
prevalence, overall PubMed retrieval precision, or external recall.

- R = evidence in title+abstract consistent with actual patient medication-taking adherence,
  persistence or refill/coverage outcome; includes historical examples.
- N = clear other-topic or absent substantive patient medication adherence evidence.
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
