# Pro_Adherence

Public code repository for the Pro_Adherence project.

Operational Stage/readiness/QA status is maintained exclusively in the project Google Drive document `07_STAGE_STATUS` (owned by `00 — Штаб`). This repository README is not a current-status source.

This repository is intentionally split from scientific working data. Raw, normalized, canonical, derived, restricted, and other research-only artifacts must remain outside this public repository. The intended durable project artifact store is the access-controlled Pro_Adherence Google Drive folder, with an independent owner-held USB backup; local execution workspaces and Drive sync caches are not a scientific source of truth. Never infer that a dataset has been migrated merely from this policy: durable identity requires an exact Drive file ID, checksum/readback and restoration evidence. Only code, contracts, small manifests/configuration, tests, documentation, and explicitly promoted public serving artifacts belong here.

Stage 0 uses exact CPython 3.13.16. The preferred independent-QA path is the digest-pinned `linux/amd64` OCI runner, which does not depend on the host Python patch version:

```bash
bash scripts/run_pre_qa_exact_runtime.sh \
  --expected-sha <EXACT_CANDIDATE_SHA> \
  --expected-parent <EXACT_PARENT_SHA> \
  --architecture-revision 22
```

A verified official-source fallback is documented in `docs/ENVIRONMENT.md`. For native exact-runtime development, install `requirements.lock` and the editable package, then the aggregate validator remains bare: `python -m pro_adherence.validate stage0`. See `docs/STAGE0_VALIDATION.md` for focused commands. Authoritative scientific and technical decisions live in the project documentation; this repository implements them and does not replace them.


Stage 0 deterministic build/restore acceptance is `env -u PYTHONPATH python scripts/stage0_e2e.py`. It materializes only an explicitly promoted, release-selected public fixture and verifies delete/rebuild plus restore hash equality; generated output is not committed source of truth.

## Accepted Stage 1 V05 code identity (not a public data release)

The exact historically accepted offline wrapper is stored unchanged at `scripts/v05/TASK0003_V05_CANONICAL_OFFLINE_FINAL_v3.py` (SHA-256 `cb72548120bcecd8b653c98264d75ddd0c0775f841a19f479d75768f5040fced`). Its required `pubmed_evidence.py` remains pinned to historical commit `ae2dd8131fb7840ccb6f0ac9332dcf31ee4776ea` / blob `994879fcc9ee6e1b526f4c51fff296dcdf8ecd79`, not the different current `main` blob. The final QA04 B v7 program is preserved unchanged at `scripts/v05/QA04_V05_B_RESTORE_NO_COPY_v7.py` (SHA-256 `36341b7a3c744d24ec03d69bc9bfa73f684bbcbc6db1daffbab99dfdc5ee0ca4`); historical QA acceptance belongs to its original evidence, not any new test claim.

The optional `scripts/v05/run_portable.py` is a path-parameterized launcher, not a new scientific algorithm. With exact Python 3.13.16, a mounted, checksum-verified private V05 source package, a clean writable ephemeral work directory, the exact historical Git checkout, and pinned dependencies, invoke:

```text
python scripts/v05/run_portable.py --source <DRIVE_MOUNTED_V05_SOURCE> --work <EMPTY_WORKSPACE> --checkout <EXACT_HISTORICAL_CHECKOUT> --deps <PINNED_DEPS>
```

It requires exact frozen-script bytes before execution and checks accepted canonical manifest and SQLite digests after the offline build. A full 753-file hash comparison and independent mounted-data clean-path execution are **not** established by committing this launcher. All private data stays outside GitHub; Stage/QA and release permissions are governed only by the Google Drive `07_STAGE_STATUS` and explicit project decisions.
