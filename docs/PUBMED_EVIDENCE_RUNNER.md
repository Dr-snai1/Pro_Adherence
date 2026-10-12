# Scoped PubMed/NCBI evidence runner — contract v1

Technical baseline: `TECHNICAL_ARCHITECTURE` revision **23**, §§8.3, 8.5, 8.6, 10.1, 10.5, 10.10, 11.8, 12.2. This is an infrastructure transport only. Current Stage/QA status is owned by Drive `07_STAGE_STATUS` (not by this file).

## Scope and provenance

A manual GitHub Actions `workflow_dispatch` invocation in public **code** repo `Dr-snai1/Pro_Adherence` runs Python CLI `pro_adherence.pubmed_evidence` on a standard GitHub-hosted runner. `permissions: contents: read`; no `push`, `pull_request`, or `schedule` on this workflow. Writer clones only the approved, **private** `Dr-snai1/Pro_Adherence-research-evidence`; fresh verifier is a separate job with its own read-only deploy key. Neither evidence contents nor secrets may be included in public repository, Pages, logs, or Actions artifacts. No embeddings, clustering, graph analysis, canonical corpus, or production serving.

The code intentionally contains **no TASK-0003 scientific queries**. Only the exact frozen query artifact from TASK-0002/TASK-0003, reviewed by 01, can create a later, explicitly pinned `configs/pubmed/*.json` versioned full-mode input. Do **not** rewrite the query, translate it, or treat its execution as an accept/revise scientific verdict. NCBI Search Details/translation/warnings are stored unchanged in raw responses and parsed mirrors. The default `configs/pubmed/smoke.v1.json` uses a short neutral infrastructure test query, never the scientific workload. All query bytes are preserved in `queries/<logical_id>.txt`.

## Run-spec and deterministic identity

The versioned JSON spec includes `schema`, `task_id`, immutable `query_artifact` ref, logical `queries` map of **exact strings**, `operation: esearch-pmids`, `partition_policy: pubdate-bisect/v1`, inclusive date bounds, and explicit non-secret config refs (`NCBI_TOOL`, `NCBI_EMAIL`, optional `NCBI_API_KEY`). The executor also pins mode, Git commit SHA, runtime identity and attempt `1` (attempt is not mutable at retry; a correction requires a new versioned run-spec). Canonical JSON (UTF-8, sorted keys, compact separators) is SHA-256 hashed to derive `r-<32 hex>` run identity. A changed query/code/runtime creates a different ID; mutable wall-clock time is never an ID. Multiple attempts with the same identity cannot overwrite a final package; corrections need a new spec/attempt/version.

All requests use HTTPS ESearch POST, explicitly set `tool`/`email`, bound timeout (35 sec), bounded retry on 429/500/502/503/504/transient failures and ≤3 requests/s without an API key (≥0.36s spacing). Do not log HTTP request bodies or secret-bearing URLs. See [official NCBI E-utilities Help](https://www.ncbi.nlm.nih.gov/books/NBK25499/) and [NCBI usage guidance](https://eutilities.github.io/site/API_Key/usageandkey/).

PubMed **10,000-UID ceiling** is not bypassed using `retstart` or `usehistory`. Queries with source count ≥10,000 are recursively partitioned by *nonoverlapping inclusive publication dates*; each leaf must have count <10,000. Any single date retaining ≥10,000 fails closed. Raw count and ID responses are written before parsing. Reconciled PMID sets are positive decimal IDs, unique, numerically ascending, newline delimited; partition counts, duplicate counts and query-level unique union must agree with the source total. Publication-date omissions/out-of-range records cause a mismatch and **failure**, never silent loss. Root errors and warnings are preserved. This is a defensive, not scientifically validated, partition policy.

## Evidence layout and manifest

Approved path: `pubmed/{task_id}/{run_id}/` in **private** evidence repository; access class `project-internal`.

- `manifest.json`: schema/status, code/runtime, pinned query hashes/refs, timestamps, NCBI endpoint/method/tool/email, partition policy, file inventory (`SHA256`, bytes), reconciliation and root SHA-256.
- `queries/`: exact submitted UTF-8 queries; `raw/`: raw JSON response bytes; `pmids/`: canonical leaf and union files; `partitions/plan.json`: exact leaf queries and date boundaries; `reconciliation.json`: source count / unique count / duplicates / union hash; `metadata/requests.json`: endpoint, method, timestamp, query hash, response file. The optional `sample_policy` maps logical query IDs to an explicit `size` (1–100) and `sha256_prefix`; the PMID sample order is SHA256(prefix + PMID), and only NCBI EFetch PubMed XML is retrieved (no full texts). The raw XML is stored under `raw/`, its canonical PMID set under `samples/`; no scientific relevance classification occurs here.
- `samples/` is populated only when the separately authorized frozen spec declares `sample_policy`; EFetch stores PubMed XML (bibliographic metadata, titles, available abstracts), and validates PMID membership. A zero-result sampled query is a **valid final infrastructure state**: an empty `samples/{qid}.pmids.txt` is written, EFetch is **not called**, and **no sample XML** exists; this is not an empirical precision judgement. That judgement remains 01/TASK-0003’s responsibility. The SHA256 prefix must be copied verbatim from the frozen sampling protocol, not chosen by the runner.

Manifest root hash is `SHA256(canonical JSON of manifest with package_root_sha256 absent)`. `manifest.json` is excluded from file inventory to avoid recursion. Verify recomputes all file hashes, root hash, exact expected set of files derived from request/partition provenance (not merely declared inventory), source/leaf/union counts and numeric-sorted-unique PMID invariants. Strict allowlist of path IDs; symlink/path traversal and unexpected files rejected. Each final package ≤50 MiB, private repository must remain <1 GiB; no LFS, overwrite or force-push. Git evidence is **not** the canonical research raw/corpus store.

## Running, verification, and owner-local backup

Local smoke (requires real NCBI network and non-secret project contact configuration):

```bash
export NCBI_TOOL='your-registered-tool' NCBI_EMAIL='project-contact@example.org'
python -m pro_adherence.pubmed_evidence collect --spec configs/pubmed/smoke.v1.json \
  --out /path/to/research-temp --mode smoke --code-commit "$(git rev-parse HEAD)" \
  --runtime 'python-3.13.16/local-<platform>'
```

Actions → **Manual PubMed evidence retrieval** → `workflow_dispatch` with `task_id=TASK-0004`, `run_spec=configs/pubmed/smoke.v1.json`, `mode=smoke`. Full mode is **not** to be launched without explicit task owner request and pinned scientific run-spec.

Provisioning owned by 00: a **private** companion repository, environment `research-pubmed`, repo variable `RESEARCH_EVIDENCE_REPOSITORY`, environment secrets `RESEARCH_EVIDENCE_WRITE_SSH_KEY` (writer only) and `RESEARCH_EVIDENCE_READ_SSH_KEY` (read-only verifier only), variables `NCBI_TOOL` and `NCBI_EMAIL`, optional secret `NCBI_API_KEY`. Keys are distinct repository-scoped deploy keys; never place secret values in docs/code/chat. Initialize the private repository's `main` branch before first write.

The writer commits under `pubmed/{task_id}/{run_id}/`, returns exact evidence Git commit and package root. A **different runner** clones that exact commit with **read-only** key and verifies from the persisted private repository, not the writer workspace. Then the owner must create an independent local/research backup on a separate physical machine/storage:

```bash
# On owner-controlled research machine, with read-only SSH access to private evidence repo:
python -m pro_adherence.pubmed_evidence backup \
  --repository Dr-snai1/Pro_Adherence-research-evidence \
  --commit '<EXACT_EVIDENCE_COMMIT_SHA>' --task-id TASK-0004 --run-id '<EXACT_RUN_ID>' \
  --target data/research/evidence
```

The backup helper clones the exact commit, recomputes hashes and counts, copies to `data/research/evidence/pubmed/{task_id}/{run_id}/` and verifies again. Verification record (`<run_id>.backup-verification.json`) must remain **outside public repo**. GH Actions cache/artifacts are neither primary nor backup. Until real NCBI response + private Git commit + fresh readback + owner-local backup all PASS, mark infrastructure **NOT ACCEPTED** and do not route scientific gate to 01.

## Durable checkpoint state machine, correction and failure semantics (ADM-001)

The common **integrity gate** is `verify(package, require_final=False)`, also invoked by `git_write()` and before any resume network activity. Manifest schema `pubmed-evidence/v1` contains `query_states` for **every** frozen logical query and a failure marker on incomplete runs. States are `not_started` (query bytes pinned, no raw/derived artifacts), `in_progress` (transient execution state, not a persisted checkpoint), `completed` (fully reconciled ESearch results and any sample), and `failed_checkpointable` (one interrupted query with failure stage/class recorded). In the persisted incomplete state, previously finished queries are `completed`, the interrupted query is `failed_checkpointable`, and later queries are `not_started`. All `queries/{qid}.txt` are materialized **before the first request**, including queries not yet started. No missing completed-query files are excused as not-started.

**Persistable incomplete failures:** pre-response ESearch or EFetch outages, an unsplittable ≥10,000 single-day partition, malformed ESearch/EFetch responses, unexpected sample XML root, sample PMID mismatch, and fail-closed reconciliation/partition errors. The collector writes a hashed `incomplete` manifest and preserves any raw response received **before parsing**. A pre-response outage has no fabricated raw file; its failure marker still identifies the affected query/stage. I/O failures that prevent writing a manifest or that prevent the integrity verifier from passing are **not** claimed as durable. A returned response that fails validation is *evidence of failure*, never silently accepted as a completed query/sample. Collect raises; the writer still attempts the private append-only checkpoint commit and then fails its job.

Every raw ESearch JSON response and raw EFetch XML response has an exact request metadata record with endpoint, method, timestamp, query/selection hash, file path and explicit outcome. Rejected parseable or malformed sample XML remains immutable at `raw/{qid}-sample.xml` (attempt 1) or `raw/{qid}-sample-00002.xml`, `-00003.xml`, etc. A retry creates the **next** immutable attempt; it never overwrites a previous failed attempt. Successful final sample selection comes only from the last **accepted** XML attempt, with exact frozen PMID identity. Previous failed XML attempts can coexist with this successful final response and retain their own provenance. The no-response EFetch outage has no XML attempt record until bytes actually arrive. ESearch requests are likewise append-only, with outcome/provenance and deterministic sequence numbers.

**Partial verifier:** exact manifest identity/schema, state consistency, safe file inventory/no symlinks, all file byte sizes/SHA256/root hash, all known query hashes, immutable response provenance, raw ESearch parse/outcome and raw-to-derived PMID/count reconciliation for every completed partition, all completed-query unions, and semantically declared rejected sample XML evidence. A not-started query may have *only its exact query file*. An interrupted query may legitimately lack unfinished PMID unions or an accepted sample; verified completed artifacts remain strict. Corrupt/missing content in any declared completed artifact is rejected. **Final verifier:** requires every query `completed`, complete partition/date coverage, exact counts/PMID unions, valid successful last XML attempt for each non-empty sample, zero-result empty sample without XML, and no pending failure state. Hashes alone never establish raw/derived consistency: verifier reparses ESearch count/idlist and matches accepted source evidence with stored derived counts/PMIDs; a rehashed but source-inconsistent package is rejected.

**Resume order:** (1) fetch/copy the private checkpoint; (2) verify complete stored hashes, root, provenance and declared partial-state semantics; (3) independently match spec/query/code/runtime identity; **only then** (4) issue new network calls. Recount unfinished partitions, reuse hash-verified leaves if their counts agree; reuse already reconciled query PMIDs for a failed sample stage; skip completed sample retrieval; retry only unfinished/failed stages. An old failed sample response is never accepted or overwritten. A new ordinary Git commit contains updated derived checkpoint metadata and any new immutable responses; Git history is append-only and `--force` is forbidden. Neither earlier checkpoint commits nor a final package can be overwritten. Changed counts, mutated stored identity, corrupt completed artifacts or changed partition plan reject before unsafe reuse.

For an empty selected sample, the declared zero-result policy is **final + empty sample PMID file + no EFetch + no sample XML**. No inference about scientific precision follows from this infrastructure state. The runner never changes the frozen scientific sampling policy on its own.

Independent owner backup after **final** exact-commit readback remains required. Tests of temporary bare Git are offline implementation regression evidence only, *not* HOFF-0019 provisioning, real NCBI smoke, private-production write, independent readback, or owner-local backup acceptance. All such infrastructure acceptance gates remain separate and unverified until actual operational evidence arrives.

## Candidate admission and Stage 0 regression boundary

TASK-0004 rev2 candidate is based on the accepted immutable Stage 0 main commit `c0917885d565348df47417ba34516e79d2e049c9` and pinned `TECHNICAL_ARCHITECTURE revision 23`. The existing `PRE_QA_GATE` Stage 0 history document must continue to reference its original Stage 0 parent `6d81685431b11bbf8fa4d4410fa5945921c1b49a` rather than any later code candidate parent; the preflight separately verifies the candidate’s actual Git parent. Independent QA remains required under `01_PROJECT_RULES v0.3`, and the live status remains solely in `07_STAGE_STATUS`.

## TASK-0007 replacement candidate admission boundary

For the TASK-0007 direct-child atomic replacement of the rejected TASK-0005/PR #3 candidate (direct parent `c0917885d565348df47417ba34516e79d2e049c9`), `TECHNICAL_ARCHITECTURE revision 23` is the pinned implementation contract. Two **different** admission checks are mandatory: historical Stage 0 regression in `scripts/pre_qa_gate.py` with `--architecture-revision 22`, and the new candidate-level `scripts/pre_qa_task0004.py` with `--architecture-revision 23`. Both check the exact SHA and parent; the new check also executes the ADM-001 focused regressions even during static preflight and enforces the approved PubMed workflow boundary, affected source/tests/config/docs, runtime/lock, Git cleanliness, stale-status scan and research/public path restrictions. Native CI runs the full suite plus explicit ADM-001 regressions and both gates separately; the pinned OCI and source fallback runners take `--architecture-revision 22 --task0004-revision 23` to run both. The historical Stage 0 accepted revision remains 22. Rejected 4295a8f84dbb47654c05795fb9e211a9fe1c4a8d / draft PR #3 is superseded and must not be merged or considered a QA target after replacement; history remains. No Stage 0 historical handoff or architecture revision is rewritten.

Implementation self-check from the clean exact candidate checkout, with locked CPython 3.13.16 installed and `PYTHONPATH` unset:

```bash
env -u PYTHONPATH python -m unittest discover -s tests -p "test_*.py"
env -u PYTHONPATH python scripts/pre_qa_gate.py --expected-sha "$(git rev-parse HEAD)" --expected-parent "$(git rev-parse HEAD^)" --architecture-revision 22
env -u PYTHONPATH python scripts/pre_qa_task0004.py --expected-sha "$(git rev-parse HEAD)" --expected-parent "$(git rev-parse HEAD^)" --architecture-revision 23
```

**Implementation PRE_QA and executable ADM-001 regressions are not infrastructure acceptance.** HOFF-0019 provisioning, merge of workflow to default branch after separate independent QA, real NCBI neutral smoke, exact durable private evidence commit/root/count reconciliation, fresh read-only-runner readback, and owner-local independent backup hash proof remain mandatory operational gates. Before those events **infrastructure acceptance is BLOCKED**. Live Stage and QA status is held exclusively in Drive `07_STAGE_STATUS`, not this repository.
