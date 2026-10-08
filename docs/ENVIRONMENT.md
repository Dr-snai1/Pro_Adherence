# Stage 0 reproducible environment contract

> Operational Stage/readiness/QA status is maintained only in project Google Drive `07_STAGE_STATUS` (00 — Штаб). This file is an immutable/instructional runtime contract for the Stage 0 candidate, not a live status source.

## Runtime

- Exact supported interpreter for this candidate: **Python 3.13.16** (CPython).
- `.python-version` contains the same exact patch.
- `pyproject.toml` declares `requires-python = "==3.13.16"`.
- Tested CI OS: GitHub-hosted `ubuntu-latest`. Stage 0 validation itself uses only Python, Git and repository files; no production server, database or backend is required.
- Files and JSON are read/written as UTF-8. Repository commands are run from the repository root on a case-sensitive filesystem in CI.
- Git is required because PRE_QA evidence checks exact commit identity, parent provenance, tracked paths and dirty state.
- Stage 0 validation requires no secrets, credentials, production database, external API or private Google Drive access.

## Locked Python environment

`requirements.lock` exact-pins the direct runtime dependency, its transitive runtime resolution, and the build/install tooling used by the clean-checkout procedure. The initial dependency installation requires network access to the configured Python package index; after installation, Stage 0 tests and validators do not fetch schemas or project data from the network.

From a fresh checkout of the exact candidate:

```bash
python --version  # must be Python 3.13.16
python -m venv .venv
. .venv/bin/activate
python -m pip install --disable-pip-version-check -r requirements.lock
python -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e .
```

The editable package install is deliberate for this repository validator: `pro_adherence.validate` reads versioned contracts and fixtures from the same exact checkout. It is a standard installed src-layout package and removes the former hidden `PYTHONPATH=src` requirement. `requirements.lock` also preinstalls the exact build backend versions, while `--no-build-isolation --no-deps` prevents the package-install step from silently resolving a second environment.

## Verification

Official validation commands must be run without a repository `src` entry in `PYTHONPATH`. The canonical clean-checkout developer command is:

```bash
env -u PYTHONPATH python scripts/pre_qa_gate.py \
  --expected-sha <EXACT_CANDIDATE_SHA> \
  --enforce-admission-parent
```

This checks the exact SHA/clean tree, Python and installed dependency versions, package import path, required environment/lock/docs files, architecture/admission metadata, stale-status markers, tracked/public boundary paths, candidate changed paths, then runs the unit suite, focused bare validators, aggregate `stage0`, and semantic mutation audit. GitHub Actions mirrors the same install/runtime contract and runs the same gates explicitly before a static PRE_QA smoke.
