# Handoff — QA-S0-005 targeted QA rerun request

**ОТ КОГО:** 03 — Разработка  
**КОМУ:** 04 — Тестирование / QA  
**ТЕМА:** Pro_Adherence — Stage 0 / QA-S0-005 immutable model identity  
**ТИП:** targeted QA regression request / blocking defect verification

**КОНТЕКСТ:**  
Architecture decision for QA-S0-005 is now normative in TECHNICAL_ARCHITECTURE. Implementation was produced from baseline `9bf4ebe2dfdfa98c6ef93cd7dcefb18a52a0939f`.

During 03 integration verification, a commit-construction regression was detected: implementation commit `96e2e14306e41eb122dbe342fb8d714fd8806e71` accidentally replaced the repository tree and dropped 33 unrelated Stage 0 files. This was not an intended semantic change. 03 restored those exact baseline blobs in corrective commit `bb587b6b5d49050c36e2c0a931df17a04a069756`.

After restoration, the diff from baseline contains exactly the intended QA-S0-005 implementation surface plus its handoff:
- `contracts/schemas/provenance.schema.json`
- `contracts/manifests/minimal_lineage.example.json`
- `contracts/examples/model_compute_asset.example.json`
- `contracts/examples/nonmodel_compute_asset.example.json`
- `src/pro_adherence/computation_signature.py`
- `tests/test_model_identity_contract.py`
- `docs/STAGE0_PROVENANCE.md`
- `docs/STAGE0_STATUS.md`
- `docs/handoffs/QA-S0-005_IMPLEMENTATION_2026-10-08.md`

A persistent Stage 0 CI workflow was then added at `.github/workflows/stage0-tests.yml`.

QA-S0-001–004 remain independently CLOSED and must not be reopened without a new regression.

**РЕЗУЛЬТАТ / ЗАПРОС:**  
Independently verify QA-S0-005 and close it only if all architecture and regression criteria pass.

Implemented contract:
- `model_identity_hash = SHA-256(canonical_model_identity_descriptor)`;
- descriptor ordered fields: `identity_schema`, `content_digest`, `identity_namespace`, `identity_key`, `immutable_revision`;
- `identity_schema = "model-identity/v1"`;
- explicit nulls;
- `model_name` and `model_ref_id` excluded from identity descriptor;
- at least digest or immutable revision is required;
- revision requires namespace + key;
- model-backed compute requires non-null `model_ref_id` and non-null `model_identity_hash`;
- non-model compute requires both null;
- active `computation_signature.model_digest` is superseded by required nullable `model_identity_hash`;
- executable validator resolves model refs, recomputes model identity hash, checks input/config refs when supplied, and recomputes the full computation digest.

**ПРОВЕРКА:**  
Developer check A — exact committed full test suite:
- executor: GitHub Actions, workflow `Stage 0 tests`;
- run ID: `37764391921`;
- head: `c0a03ef6f93777ef5335a26920a216ec0bdf0881`;
- Python: `3.13.15`;
- jsonschema: `4.26.0`;
- command: `python -m unittest discover -s tests -p 'test_*.py'`;
- result: **15 tests, OK**;
- workflow conclusion: **success**.
This suite includes the previously closed QA-S0-001–004 regression tests plus QA-S0-005 tests.

Developer check B — independent helper-free SHA-256 recomputation:
- committed model descriptor recomputed to `2e75c08ef87dbe230d94964dbaa8117bb44c9269ecc4bc1b1f82712e75f2cdaf`;
- committed model computation signature recomputed to `956ff79188aef5492698f12d75ccfe70e0e910b9fefb3fc41fc09e98e13a365b`;
- committed non-model signature recomputed to `6dfdc633ffaf7cef7b7c02182340bb19f4f1560b55a8051a031f785075dd1fe4`;
- changing revision changes identity hash;
- changing content digest changes identity hash;
- display/model name is not part of the descriptor.

Repository restoration check:
- source = baseline tree `9bf4ebe…` and current tree after `bb587b6…`;
- method = exact Git blob/tree diff;
- result = all 33 unintentionally dropped baseline files restored by original blob SHA;
- interpretation = accidental tree replacement corrected without changing their contents.

**ИСТОЧНИКИ:**  
- TECHNICAL_ARCHITECTURE §§4.1, 6.1, 6.3, 6.4, 7.2–7.3, Appendix B;
- 01_PROJECT_RULES;
- 05_DEVELOPMENT_SETUP;
- 06_TESTING_QA_SETUP;
- STAGE0_INDEPENDENT_QA_2026-10-08 / QA-S0-005;
- GitHub baseline `9bf4ebe2dfdfa98c6ef93cd7dcefb18a52a0939f`;
- implementation `96e2e14306e41eb122dbe342fb8d714fd8806e71`;
- restoration `bb587b6b5d49050c36e2c0a931df17a04a069756`;
- CI workflow commit/run head `c0a03ef6f93777ef5335a26920a216ec0bdf0881`, run `37764391921`;
- `docs/STAGE0_MODEL_IDENTITY_MIGRATION_2026-10-08.md`.

**ЧТО ИЗМЕНИЛОСЬ:**  
QA-S0-005 implementation now uses canonical `model_identity_hash`; model-backed and non-model fixtures and executable validator exist; full regression suite is executable in GitHub Actions. A separate migration note records `model_digest → model_identity_hash`. The accidental unrelated deletions introduced by the temporary implementation commit were fully restored.

**ЧТО ОБНОВИТЬ:**  
04 — QA should update QA-S0-005 defect status and evidence after independent targeted rerun. If PASS, mark QA-S0-005 CLOSED. Do not infer that overall Stage 0 is release-ready: remaining validator/build/E2E criteria still require completion and independent acceptance.

**ОТКРЫТЫЕ ВОПРОСЫ:**  
No architecture question remains for QA-S0-005. Overall Stage 0 remains OPEN because cross-record repository validator/gates, full build/validation flow, and final E2E acceptance remain incomplete.

**СЛЕДУЮЩЕЕ ДЕЙСТВИЕ:**  
04 — Тестирование / QA independently reruns QA-S0-005 cases, executes the committed test suite, checks model-identity hashing and the restoration/no-regression condition, and returns PASS/FAIL with evidence to 03 — Разработка.

Until independent closure: **QA-S0-005 = OPEN / BLOCKING; Stage 0 = OPEN / NOT RELEASE-READY.**
