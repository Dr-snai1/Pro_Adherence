# QA-S0-005 developer handoff — 2026-10-08

ОТ КОГО: Temporary Stage 0 implementation chat.
КОМУ: 03 — Разработка.
ТЕМА: Immutable model identity / computation signature.
ТИП: Implementation handoff; NOT QA acceptance.

КОНТЕКСТ: Approved TECHNICAL_ARCHITECTURE model identity decision, baseline main@9bf4ebe2dfdfa98c6ef93cd7dcefb18a52a0939f.
РЕЗУЛЬТАТ: Contract, canonical helper/validator, fixtures and targeted regression tests committed to main; independent QA pending.
ПРОВЕРКА: GitHub readback of committed schema/helper/tests; independent Python hashlib fixture identity and null-model signature recomputation. Full committed unittest suite NOT RUN here because repository clone/network unavailable; no test PASS or exit code is claimed.
ИСТОЧНИКИ: Drive TECHNICAL_ARCHITECTURE §§4.1, 6.1, 6.3, 6.4, 7.2–7.3 Appendix B; 01_PROJECT_RULES; 05_DEVELOPMENT_SETUP; 06_TESTING_QA_SETUP; STAGE0_INDEPENDENT_QA_2026-10-08; GitHub repository main.
ЧТО ИЗМЕНИЛОСЬ: provenance schema; minimal lineage model_ref; executable model identity helper; model and nonmodel compute fixtures; targeted regression tests; STAGE0_PROVENANCE and STAGE0_STATUS. Existing QA-S0-001–004 contracts were not intentionally changed.
ЧТО ОБНОВИТЬ: After developer test execution, record environment, actual result count and exit code here; then send to 04 — QA for independent rerun.
ОТКРЫТЫЕ ВОПРОСЫ: Independent executable testing and schema↔fixture↔test acceptance remains unverified. Existing non-model fixture uses SHA-256 over five-field compact JSON with explicit null; all artifacts are synthetic.
СЛЕДУЮЩЕЕ ДЕЙСТВИЕ: Run:
```bash
python -m pip show jsonschema
python -m unittest discover -s tests -p 'test_*.py' -v
```
Then separately recompute identity + computation digests with helper-independent code and compare fixtures. If failures, fix before targeted independent QA.

Implemented model fixture identity hash: `2e75c08ef87dbe230d94964dbaa8117bb44c9269ecc4bc1b1f82712e75f2cdaf`.
Implemented model computation digest: `956ff79188aef5492698f12d75ccfe70e0e910b9fefb3fc41fc09e98e13a365b`.
Nonmodel computation digest: `6dfdc633ffaf7cef7b7c02182340bb19f4f1560b55a8051a031f785075dd1fe4`.
Local recomputation environment: Python 3.13.5; jsonschema 4.26.0 (jsonschema not used for SHA-256 recomputation).

Previous `computation_signature.model_digest` is **superseded**, not silently accepted. Historical records require explicit migration.

Implementation commit: `96e2e14306e41eb122dbe342fb8d714fd8806e71`.
Additional fixture/test commits: `7f00754067ff375d6ced99a78a4eb34ef7c52f00`, `44e3bc237246b7ccaf6a9efc90d88bb481b8c572`.
QA-S0-005 = OPEN / BLOCKING; Stage 0 = OPEN / NOT RELEASE-READY.
