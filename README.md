# Pro_Adherence

Public code repository for the Pro_Adherence project.

Operational Stage/readiness/QA status is maintained exclusively in the project Google Drive document `07_STAGE_STATUS` (owned by `00 — Штаб`). This repository README is not a current-status source.

This repository is intentionally split from scientific working data. Raw, normalized, canonical, derived, restricted, and other research-only artifacts are local/off-repository by default. Only code, contracts, small manifests/configuration, tests, documentation, and explicitly promoted public serving artifacts belong here.

Stage 0 setup uses the exact environment contract in `docs/ENVIRONMENT.md`: Python 3.13.16, `requirements.lock`, then an installed editable package. After installation the aggregate validator is bare:

```bash
python -m pro_adherence.validate stage0
```

For formal developer PRE_QA evidence, run `scripts/pre_qa_gate.py` with the exact candidate SHA. See `docs/STAGE0_VALIDATION.md` for focused commands and `docs/ENVIRONMENT.md` for the clean-checkout sequence. Authoritative scientific and technical decisions live in the project documentation; this repository implements them and does not replace them.
