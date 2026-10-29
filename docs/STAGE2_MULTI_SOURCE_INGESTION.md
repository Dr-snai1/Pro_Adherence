# Stage 2 — multi-source ingestion: initial runnable slice (2026-10-29)

Authority: 07_STAGE_STATUS = Stage 2 OPEN; scientific scope in 02_SCIENTIFIC_GUIDANCE; architecture rev23 §12.3. These are technical notes, not a new search strategy, scientific result, or Stage gate.

## Access and acquisition decision

- PubMed: accepted frozen V05 private corpus is an immutable input. Never repeat its ESearch/EFetch or put private bytes into public GitHub.
- Web of Science Core Collection: owner supplied https://www.webofscience.com/wos/woscc/basic-search . External automated GET returned HTTP 403; this is NOT evidence about the owner's signed-in institutional account. Verify actual subscription and authorized export entitlement in the authenticated session. The documented native interface supports tagged plain-text export. Select Full Record and Cited References where allowed; Clarivate support describes a 500-record per-export limit for this format, subject to actual subscription UI. Do not scrape, copy cookies, or assume an API key. Web of Science API Expanded requires a separate paid license and is not authorized here.
  - https://webofscience.help.clarivate.com/en-us/Content/export-records.htm
  - https://support.clarivate.com/ScientificandAcademicResearch/s/article/Web-of-Science-Limit-on-exporting?language=en_US
  - https://developer.clarivate.com/apis/wos
- APA PsycINFO: approved scientific source, but access platform not verified. APA lists PsycNet, EBSCOhost, Ovid, ProQuest. Determine actual platform, license and export format before making its own real adapter; do not treat WoS tagged text as PsycINFO.
  - https://www.apa.org/pubs/databases/access
  - https://www.apa.org/pubs/databases/psycinfo/faq

No authentication bypass, commercial API purchase, public restricted data upload, or public promotion. All actual exports and license evidence must remain in authorized private Drive/local research storage with exact file ID, byte SHA256, acquisition time, full query and translations, export settings, covered batch ranges, provenance and permissions. Access class defaults restricted-license.

## Initial runnable unit (code-only public GitHub)

- src/pro_adherence/stage2_sources.py: parse_wos_tagged_export(payload) accepts WoS tagged UTF-8 plain-text export, including FN/PT/UT/ER/EF and selected bibliographic fields, verifies completeness and unique UT. Preserves raw byte SHA256, source record ID and raw record ordinal; unknown raw fields remain only in original private export.
- reconcile_sources() makes a PROVISIONAL cross-source identity view using exact normalized DOI/PMID only, rejects contradicting identifier merges, retains source memberships, source reference pointers, exact-DOI citation links and unresolved references. Titles cannot force merge. Raw authors/affiliations remain source statements; no unsupported author disambiguation.
- leave_one_source_out() deterministically recomputes omitted-source views without hand edits. Synthetic tests are not scientific evidence and do not imply actual WoS/PsycINFO integration.
- The importer intentionally preserves non-article source records privately; downstream accepted article-only, English and medication-only criteria require separate versioned source-specific filtering and a scientifically reviewed WoS query translation.

## Next safe integration unit

1. Verify signed-in WoS access and allowed export/reuse, record precise WoS Core Collection index selection, topic/title fields, search-history and date; do not mechanically equate PubMed query syntax with WoS.
2. Obtain one small legitimately exported Full Record and Cited References WoS sample in private storage, hash and read back, parse offline, assess missing fields/coverage and source provenance; only after that plan batched export and reconciliation.
3. Verify APA PsycINFO provider/license/export format; build separate adapter.
4. Ingest accepted private V05 + authorized WoS/PsycINFO source records into versioned cross-source identity and citation views; test source leave-one-out, lineage, ambiguity, author/affiliation and license boundary, then seek independent QA04 at integrated milestone.

## Checks

Synthetic tests: PYTHONPATH=src python -m unittest discover -s tests -p test_stage2_sources.py (does not access network). Developer verification requires targeted test run and independent readback of committed file+tests+docs from GitHub. No actual WoS/PsycINFO user records, paid API credential, signed-in entitlement or complete source mapping have been established. No Stage 2 release or new public promotion is claimed.
