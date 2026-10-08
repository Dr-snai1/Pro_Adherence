# Stage 0 reproducible environment contract

> Operational Stage/readiness/QA status is maintained only in project Google Drive `07_STAGE_STATUS` (00 — Штаб). This file is an immutable/instructional runtime contract for the candidate, not a live status source.

## Exact runtime identity

The supported interpreter is **CPython 3.13.16**. `.python-version` and `pyproject.toml` carry the same exact patch requirement. Official acceptance commands run without a repository `src` entry in `PYTHONPATH`.

The primary independent-QA envelope is the Docker Official Image for Python, pinned by immutable platform manifest rather than a mutable tag:

- platform: `linux/amd64`
- image identity: `python@sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024`
- human-readable upstream tag at verification time: `python:3.13.16-slim` (informational only; never used as acceptance identity)
- required first command inside the container: `python --version`, expected exactly `Python 3.13.16`

`scripts/run_pre_qa_exact_runtime.sh` selects Docker or compatible Podman, pulls by digest with `--platform linux/amd64`, mounts only the repository checkout read-only, verifies the mounted candidate SHA and clean tree from inside the container, clones that checkout into ephemeral container storage, installs the locked environment/package, and executes the complete acceptance/preflight flow. Host `PYTHONPATH` is not forwarded, no home/SSH/Drive credentials or Docker socket are mounted, and the container is removed after the run.

Example from the exact candidate checkout:

```bash
bash scripts/run_pre_qa_exact_runtime.sh \
  --expected-sha <EXACT_CANDIDATE_SHA> \
  --expected-parent <EXACT_PARENT_SHA> \
  --architecture-revision 22
```

The runner itself contains the literal pinned digest and the literal `--platform linux/amd64` pull/run commands; a tag-only invocation is not an acceptance path. The slim image does not carry Git, so the ephemeral container installs Debian `git` only as a checkout-verification utility after the Python version check. This does not become a project runtime, serving dependency, or production infrastructure component.

## Locked Python environment

`requirements.lock` exact-pins direct/transitive Python packages and build/install tooling. Install it with dependency resolution disabled, then install the project without build isolation or dependency resolution:

```bash
python -m pip install --disable-pip-version-check --no-deps -r requirements.lock
python -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e .
```

The current lock is version-pinned rather than pip `--require-hashes`. Hash mode was assessed for this remediation and deferred because the same lock is intentionally consumed by the immutable `linux/amd64` OCI path, native exact-3.13.16 CI, and the source-build fallback; a complete hash lock would need an explicitly maintained set of all permitted wheels/source distributions across those paths. Introducing a partial/single-artifact hash set would either reject a supported fallback or silently narrow the environment contract. Residual risk is explicit: package file bytes are not content-addressed by this lock. The exact OCI runtime remains content-addressed by digest, and pip is prevented from resolving unlisted transitive package versions by `--no-deps`.

The initial package installation requires network access to the configured Python package index. After installation, Stage 0 tests and validators do not fetch project schemas/data from the network. Files and JSON are UTF-8; Git is required for exact SHA/parent/dirty-state evidence. No secrets, production database, external API credentials, or private Google Drive access are required.

## Native exact-runtime developer path

Where CPython 3.13.16 is already available:

```bash
python --version  # must be Python 3.13.16
python -m venv .venv
. .venv/bin/activate
python -m pip install --disable-pip-version-check --no-deps -r requirements.lock
python -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e .
env -u PYTHONPATH python scripts/pre_qa_gate.py \
  --expected-sha <EXACT_CANDIDATE_SHA> \
  --expected-parent <EXACT_PARENT_SHA> \
  --architecture-revision 22
```

`scripts/pre_qa_gate.py` checks the exact SHA and explicit parent supplied at runtime; no admission parent is hardcoded in the script.

## Official-source fallback when Docker/Podman is unavailable

The fallback uses the official CPython source release and verifies it before extraction/build:

- version: `Python 3.13.16`
- source: `https://www.python.org/ftp/python/3.13.16/Python-3.13.16.tar.xz`
- SHA-256: `f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d`

Run:

```bash
bash scripts/run_pre_qa_source_fallback.sh \
  --expected-sha <EXACT_CANDIDATE_SHA> \
  --expected-parent <EXACT_PARENT_SHA> \
  --architecture-revision 22
```

The script downloads to a temporary directory, verifies SHA-256 **before** extraction, builds into an isolated temporary prefix, verifies `Python 3.13.16`, creates a clean venv, clones the exact clean candidate into temporary storage, installs the same lock/package, and runs the same unit/focused/stage0/mutation/PRE_QA flow.

This fallback is not promised on a host lacking a compiler or development libraries. At minimum it requires `git`, `make`, `tar` with XZ support, a C compiler, `curl` or `wget`, and `sha256sum` or `shasum`. A practical Debian/Ubuntu build host should also provide the normal CPython development headers/libraries, including OpenSSL, zlib, bz2, libffi, lzma, readline, SQLite and ncurses development packages. Missing optional modules or TLS support will fail the build/install path rather than be silently accepted.

## Scope boundary

OCI/source runtimes are QA/reproducibility execution envelopes and clean-room verification mechanisms only. They are not the production backend, serving dependency, recurring paid infrastructure, or research-compute service. The zero-cost static-first architecture is unchanged.


## Stage 0 deterministic build/materialization envelope

The runtime contract also covers the minimal Stage 0 public build. After package installation, `python scripts/stage0_e2e.py` constructs a synthetic promoted fixture from committed inputs, validates the exact corpus/lineage/promotion evidence, materializes only release-selected public payloads, deletes and rebuilds the serving bundle byte-for-byte, performs the minimal restore drill, and independently recalculates the final tree hash. Generated serving directories are temporary evidence and are not repository source of truth.

The materializer is an installed-package CLI (`python -m pro_adherence.materialize`) and does not use a production database, server, credentials, raw/research directory scan, or hidden `PYTHONPATH`. Its input mapping is exact: every selected release artifact must have exactly one payload source and extra/unselected payload sources fail closed.
