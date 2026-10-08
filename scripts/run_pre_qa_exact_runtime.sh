#!/usr/bin/env bash
set -euo pipefail

IMAGE='python@sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024'
PLATFORM='linux/amd64'
EXPECTED_SHA=''
EXPECTED_PARENT=''
ARCHITECTURE_REVISION=''

usage() {
  cat <<'EOF'
Usage: scripts/run_pre_qa_exact_runtime.sh \
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

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo 'run from a Git checkout' >&2; exit 2; }
cd "$ROOT"

if [[ -n "${QA_CONTAINER_ENGINE:-}" ]]; then
  ENGINE="$QA_CONTAINER_ENGINE"
  [[ -x "$ENGINE" ]] || { echo "QA_CONTAINER_ENGINE is not executable: $ENGINE" >&2; exit 2; }
elif command -v docker >/dev/null 2>&1; then
  ENGINE="$(command -v docker)"
elif command -v podman >/dev/null 2>&1; then
  ENGINE="$(command -v podman)"
else
  echo 'docker or compatible podman is required; use scripts/run_pre_qa_source_fallback.sh when unavailable' >&2
  exit 127
fi

echo "PRE_QA OCI engine: $ENGINE"
echo "PRE_QA OCI platform: $PLATFORM"
echo "PRE_QA OCI image: $IMAGE"
"$ENGINE" pull --platform "$PLATFORM" "$IMAGE"

# exec is intentional: the container/acceptance exit code becomes this runner's exit code.
exec "$ENGINE" run --rm --pull=never --platform "$PLATFORM" \
  --mount "type=bind,src=$ROOT,dst=/repo,readonly" \
  --env EXPECTED_SHA="$EXPECTED_SHA" \
  --env EXPECTED_PARENT="$EXPECTED_PARENT" \
  --env ARCHITECTURE_REVISION="$ARCHITECTURE_REVISION" \
  --env PIP_DISABLE_PIP_VERSION_CHECK=1 \
  --env PIP_NO_INPUT=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --workdir /work \
  "$IMAGE" \
  sh -ec '
    python --version
    test "$(python --version 2>&1)" = "Python 3.13.16" || {
      echo "exact runtime mismatch" >&2
      exit 90
    }

    apt-get update >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git >/dev/null
    rm -rf /var/lib/apt/lists/*

    git config --global --add safe.directory /repo
    test "$(git -C /repo rev-parse HEAD)" = "$EXPECTED_SHA" || {
      echo "mounted checkout HEAD mismatch" >&2
      exit 91
    }
    test -z "$(git -C /repo status --porcelain --untracked-files=all)" || {
      echo "mounted checkout is dirty" >&2
      exit 92
    }

    git clone --quiet --no-hardlinks /repo /work/repo
    cd /work/repo
    git checkout --quiet --detach "$EXPECTED_SHA"
    test "$(git rev-parse HEAD)" = "$EXPECTED_SHA" || exit 93
    test "$(git rev-parse HEAD^)" = "$EXPECTED_PARENT" || {
      echo "candidate parent mismatch" >&2
      exit 94
    }
    test -z "$(git status --porcelain --untracked-files=all)" || exit 95

    env -u PYTHONPATH python -m pip install --no-deps -r requirements.lock
    env -u PYTHONPATH python -m pip install --no-build-isolation --no-deps -e .

    env -u PYTHONPATH python -m unittest discover -s tests -p "test_*.py"
    env -u PYTHONPATH python -m pro_adherence.validate contracts
    env -u PYTHONPATH python -m pro_adherence.validate corpus contracts/manifests/empty_corpus.manifest.json
    env -u PYTHONPATH python -m pro_adherence.validate release contracts/manifests/empty_release.manifest.json
    env -u PYTHONPATH python -m pro_adherence.validate lineage contracts/manifests/minimal_lineage.example.json
    env -u PYTHONPATH python -m pro_adherence.validate boundary
    env -u PYTHONPATH python -m pro_adherence.validate stage0
    env -u PYTHONPATH python scripts/stage0_mutation_audit.py
    env -u PYTHONPATH python scripts/pre_qa_gate.py \
      --expected-sha "$EXPECTED_SHA" \
      --expected-parent "$EXPECTED_PARENT" \
      --architecture-revision "$ARCHITECTURE_REVISION"
  '
