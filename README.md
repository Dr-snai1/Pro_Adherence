# Pro_Adherence

Public code repository for the Pro_Adherence project.

Operational Stage/readiness/QA status is maintained exclusively in the project Google Drive document `07_STAGE_STATUS` (owned by `00 — Штаб`). This repository README is not a current-status source.

This repository is intentionally split from scientific working data. Raw, normalized, canonical, derived, restricted, and other research-only artifacts are local/off-repository by default. Only code, contracts, small manifests/configuration, tests, documentation, and explicitly promoted public serving artifacts belong here.

Stage 0 uses exact CPython 3.13.16. The preferred independent-QA path is the digest-pinned `linux/amd64` OCI runner, which does not depend on the host Python patch version:

```bash
bash scripts/run_pre_qa_exact_runtime.sh \
  --expected-sha <EXACT_CANDIDATE_SHA> \
  --expected-parent <EXACT_PARENT_SHA> \
  --architecture-revision 22
```

A verified official-source fallback is documented in `docs/ENVIRONMENT.md`. For native exact-runtime development, install `requirements.lock` and the editable package, then the aggregate validator remains bare: `python -m pro_adherence.validate stage0`. See `docs/STAGE0_VALIDATION.md` for focused commands. Authoritative scientific and technical decisions live in the project documentation; this repository implements them and does not replace them.
