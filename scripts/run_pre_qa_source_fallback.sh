#!/usr/bin/env bash
set -euo pipefail

PYTHON_VERSION='3.13.16'
SOURCE_URL='https://www.python.org/ftp/python/3.13.16/Python-3.13.16.tar.xz'
SOURCE_SHA256='f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d'
EXPECTED_SHA=''
EXPECTED_PARENT=''
ARCHITECTURE_REVISION=''

usage() {
  cat <<'EOF'
Usage: scripts/run_pre_qa_source_fallback.sh \
  --expected-sha <40-hex> \
  --expected-parent <40-hex> \
  --architecture-revision <revision>
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --expected-sha) EXPECTED_SHA="${2:-}"; shift 2 ;;
    --expected-parent) EXPECTED_PARENT="${2:-}"; shift 2 ;;
    --architecture-revision) ARCHITECTURE_REVISION="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'invalid or missing --expected-sha' >&2; exit 2; }
[[ "$EXPECTED_PARENT" =~ ^[0-9a-f]{40}$ ]] || { echo 'invalid or missing --expected-parent' >&2; exit 2; }
[[ -n "$ARCHITECTURE_REVISION" ]] || { echo 'missing --architecture-revision' >&2; exit 2; }

for tool in git make tar; do command -v "$tool" >/dev/null 2>&1 || { echo "missing build prerequisite: $tool" >&2; exit 127; }; done
command -v cc >/dev/null 2>&1 || command -v gcc >/dev/null 2>&1 || { echo 'missing C compiler (cc/gcc)' >&2; exit 127; }
if command -v curl >/dev/null 2>&1; then FETCH=(curl -fsSLo); elif command -v wget >/dev/null 2>&1; then FETCH=(wget -qO); else echo 'missing curl or wget' >&2; exit 127; fi
if command -v sha256sum >/dev/null 2>&1; then HASH=(sha256sum); elif command -v shasum >/dev/null 2>&1; then HASH=(shasum -a 256); else echo 'missing sha256sum or shasum' >&2; exit 127; fi

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo 'run from a Git checkout' >&2; exit 2; }
cd "$ROOT"
test "$(git rev-parse HEAD)" = "$EXPECTED_SHA" || { echo 'HEAD mismatch' >&2; exit 91; }
test "$(git rev-parse HEAD^)" = "$EXPECTED_PARENT" || { echo 'parent mismatch' >&2; exit 92; }
test -z "$(git status --porcelain --untracked-files=all)" || { echo 'working tree is dirty' >&2; exit 93; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/pro-adherence-cpython-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
TARBALL="$WORK/Python-${PYTHON_VERSION}.tar.xz"
"${FETCH[@]}" "$TARBALL" "$SOURCE_URL"
ACTUAL_SHA="$("${HASH[@]}" "$TARBALL" | awk '{print $1}')"
test "$ACTUAL_SHA" = "$SOURCE_SHA256" || { echo "source SHA-256 mismatch: $ACTUAL_SHA" >&2; exit 94; }

# Hash verification is deliberately completed before extraction or compilation.
tar -xJf "$TARBALL" -C "$WORK"
PREFIX="$WORK/python-prefix"
cd "$WORK/Python-${PYTHON_VERSION}"
./configure --prefix="$PREFIX" --with-ensurepip=install
JOBS=2
if command -v nproc >/dev/null 2>&1; then JOBS="$(nproc)"; fi
make -j"$JOBS"
make install

PYTHON="$PREFIX/bin/python3.13"
test "$($PYTHON --version 2>&1)" = "Python 3.13.16" || { echo 'built runtime mismatch' >&2; exit 95; }

git clone --quiet --no-hardlinks "$ROOT" "$WORK/repo"
cd "$WORK/repo"
git checkout --quiet --detach "$EXPECTED_SHA"
test "$(git rev-parse HEAD)" = "$EXPECTED_SHA" || exit 96
test "$(git rev-parse HEAD^)" = "$EXPECTED_PARENT" || exit 97

"$PYTHON" -m venv "$WORK/venv"
VENV_PYTHON="$WORK/venv/bin/python"
env -u PYTHONPATH "$VENV_PYTHON" -m pip install --disable-pip-version-check --no-deps -r requirements.lock
env -u PYTHONPATH "$VENV_PYTHON" -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e .

env -u PYTHONPATH "$VENV_PYTHON" -m unittest discover -s tests -p 'test_*.py'
env -u PYTHONPATH "$VENV_PYTHON" -m pro_adherence.validate contracts
env -u PYTHONPATH "$VENV_PYTHON" -m pro_adherence.validate corpus contracts/manifests/empty_corpus.manifest.json
env -u PYTHONPATH "$VENV_PYTHON" -m pro_adherence.validate release contracts/manifests/empty_release.manifest.json
env -u PYTHONPATH "$VENV_PYTHON" -m pro_adherence.validate lineage contracts/manifests/minimal_lineage.example.json
env -u PYTHONPATH "$VENV_PYTHON" -m pro_adherence.validate boundary
env -u PYTHONPATH "$VENV_PYTHON" -m pro_adherence.validate stage0
env -u PYTHONPATH "$VENV_PYTHON" scripts/stage0_mutation_audit.py
env -u PYTHONPATH "$VENV_PYTHON" scripts/pre_qa_gate.py \
  --expected-sha "$EXPECTED_SHA" \
  --expected-parent "$EXPECTED_PARENT" \
  --architecture-revision "$ARCHITECTURE_REVISION"
