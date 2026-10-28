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

`scripts/v05/run_portable.py` is the corrected path-parameterized launcher, not a scientific rewrite. Its ONLY durable input is the **private** Drive-mounted V05 package (three bytewise archive parts plus parts manifest); scratch extraction and build may use any local temporary disk. It assembles and SHA-verifies all parts and the accepted 7z, extracts via an available `7z` / `7zz` / `7zr` binary, checks the frozen PMID, 250 raw+meta pairs, all 750 Parquet digests, accepted SQLite + manifest and its 753-file set, then seeds the frozen archived batches into a **new empty** work directory and runs the exact accepted offline code using the historical Git commit.

Required runtime: **CPython 3.13.16**, **numpy 2.3.5**, **pyarrow 26.0.0** (see `scripts/v05/requirements.lock`); accepted old module `ae2dd813...` pinned by both commit and Git blob. A single clean-path command, after installing pinned dependencies and mounting the private Drive project folder, is:

```text
python scripts/v05/run_portable.py --parts-dir <DRIVE_MOUNTED_V05_PACKAGE_FOLDER> --work <NEW_EMPTY_DISPOSABLE_WORKSPACE> --checkout <EXACT_OLD_GIT_CHECKOUT> --deps <PINNED_V05_SITE_PACKAGES> --extractor <7Z_COMMAND_OR_PATH>
```

The launcher **does not require any fixed C: path** and never writes to the mounted Drive package or the USB backup. Expected terminal scientific reproducibility marker on success: `V05_CLEAN_PATH_DETERMINISTIC_REBUILD_PASS files=753/753 network_calls=0`. `--verify-only` tests the package/restore and source/canonical hashes without making a scientific rebuild claim. The exact Drive file IDs and SHA are recorded in the accepted Drive parts manifest, not in this public code repository. Stage/QA and release permissions remain governed only by `07_STAGE_STATUS`; storing/committing the launcher is not itself proof of an actual clean runtime.
