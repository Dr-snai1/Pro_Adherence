# Versioned PubMed NOT translation fail-closed gate — technical candidate v1

Scope: query transport and replay integrity only. This does NOT approve scientific query content, sample labels or new NCBI requests. Current Stage/QA status is exclusively Google Drive 07_STAGE_STATUS.

## Source observation

Frozen TASK-0003 accepted ESearch responses for V01_D_only, V01_E_only, and PDC_incremental_only contained source warninglist.outputmessages=["NOT"]. Original queries contained AND NOT, but returned querytranslation lacked NOT. Control V01_PT_delta with standalone NOT preserved it with no warning. Old evidence is immutable; labels reflect intended, not confirmed, exclusive retrieval. PDC_incremental_only 1,870 frozen PMIDs matched PDC_all intersection S0; offline PDC_all minus S0 187, not an authoritative new live count. See Google Drive HOFF-0118.

## New future full-mode contract

A future scientifically approved full-mode run spec with lexical Boolean NOT must declare translation_guard: "pubmed-not-translation/v1". No scientific content is rewritten. The new optional key is included in the run-ID hash and in newly generated package manifests; preexisting manifests with no flag remain under their original historical verifier contract.

New full-mode AND NOT syntax is rejected because historical source responses did not preserve the intended exclusion. Suggested standalone NOT requires independent actual PubMed Search Details, set reconstruction and scientific approval. The gate checks fresh and resumed base, count, UID and date-partition responses: querytranslation must be a string containing at least the number of unquoted Boolean NOT tokens in the exact query; warninglist must be an object without independent NOT warning (and outputmessages must be a string array if present). This is only a necessary check, NOT proof of full Boolean equivalence.

Save original bytes first, then reject a dropped-NOT response with existing rejected/incomplete evidence semantics; NEVER treat it as an accepted count, UID leaf or scientific sample. Verification of a guarded immutable package independently replays this rule against saved raw even if package hash inventory is recomputed. Historical frozen packages remain byte-valid under the original no-guard transport contract, but old sample labels must not be promoted as scientific truth.

## Tests and boundary

Synthetic tests in tests/test_pubmed_not_guard.py check explicit versioned policy, strict AND NOT admission, historical unguarded traces, emitted rejected incomplete evidence, valid new NOT-positive two-request search, rehashed raw translation corruption and parser metadata failure. No actual HTTP, NCBI, secrets, scientific specs or workflow dispatch. Old source, data and production serving are unchanged.

After technical QA, the next scientific task is to version corrected query strings and examine returned PubMed querytranslation/warnings and reconstructed set differences, then collect new source-validated samples for manual Check A/B. Do not assume the source will preserve standalone NOT without observing it.
