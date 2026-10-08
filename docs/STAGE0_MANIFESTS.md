# Stage 0 corpus and serving release manifests

Status: QA-S0-004 independently verified and CLOSED. Stage 0 overall remains OPEN; executable manifest reconciliation is implemented developer-side and awaits independent QA.

Corpus validation now checks article_count, duplicate canonical IDs, exact input-artifact hashes, readable inclusion/exclusion policy bytes and hashes, and canonical manifest_hash recomputation.

Release validation now checks canonical manifest_hash, exact artifact resolution (ID/hash/schema version/type where present), publication permission against the artifact catalog, corpus compatibility, promotion-event target/decision/coverage, referenced quality-report existence and unique producing-run lineage for promoted artifacts.

The validator intentionally does not require quality_report.status = pass until 02 — Technical Architecture makes that exact promotion semantic explicit.