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

## First owner-supplied WoS export: bounded local pilot (2026-10-29)

The owner uploaded a legitimate-looking WoS Core Collection plain-text export named savedrecs.txt to the active private conversation. This is NOT independent confirmation of subscription scope, transfer rights or completeness of the full retrieval. The raw text (including names, emails, abstracts and references) is NOT published to GitHub. The exact uploaded raw byte content is preserved only as the conversation attachment, not yet in the long-term restricted research store.

- Uploaded file bytes: 38,127; SHA-256 a05af1f6ec9f338d3f94a136eb639e0540e42d44156d1ebcf928bb61f80bffa7.
- FN/VR header and EF end marker present; 10 complete ER records; 10 distinct WOS: UT; 10 English.
- Source DT distribution: Article 7, Meeting Abstract 2, Editorial Material 1. Article-only filtering is a DERIVED, not destructive, view. This pilot cannot be described as 10 eligible journal articles.
- DOI 8 (all distinct), PMID 4, abstract 7; 191 individual CR cited references with each record's NR count exactly matching the corresponding CR list (total NR=191). The first parser implementation erroneously concatenated all indented CR items within each article into one string; repaired in later commit and added regression for CR/NR integrity. Other indented fields remain joined as continuations.
- Verification method A: parse the actual owner-supplied raw UTF-8 bytes with independent structural tag/continuation/record-boundary checks, UT dedupe, and per-record NR versus CR counts.
- Verification method B: targeted CI synthetic tests against the fixed code (no raw licensed data in public CI), plus readback of exact code and test blob SHA from the branch. These two checks have different scopes; the actual uploaded file has not yet been rerun using the code inside the owner's authenticated WoS session.
- The earlier six-term exploratory Topic search gave 35,751 hits per user screenshot and is NOT the accepted final WoS translation/frozen retrieval. It must not be treated as the complete agreed search strategy or as an approved acquisition volume.

Next: versioned translation and validation of the entire accepted medication-only scientific search blocks into WoS syntax, then a minimal legitimately authorized full-record+cited-reference sample and private immutable archival, before any large-scale WoS ingestion. Publication permission stays FALSE.
