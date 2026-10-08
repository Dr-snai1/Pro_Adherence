#!/usr/bin/env python3
"""Machine-checkable Stage 0 PRE_QA preflight."""
import argparse, importlib.metadata as md, os, re, subprocess, sys, tomllib
from pathlib import Path

R = Path(__file__).resolve().parents[1]
A = 'docs/handoffs/PRE_QA_STAGE0_PORTABLE_RUNTIME_2026-10-08.md'
EXPECTED_PYTHON = (3, 13, 16)
L = {
    'attrs': '25.4.0',
    'jsonschema': '4.26.0',
    'jsonschema-specifications': '2025.9.1',
    'pip': '25.2',
    'referencing': '0.36.2',
    'rpds-py': '0.27.1',
    'setuptools': '80.9.0',
    'wheel': '0.45.1',
}
REQ = (
    '.python-version', 'pyproject.toml', 'requirements.lock',
    'docs/ENVIRONMENT.md', 'docs/STAGE0_VALIDATION.md',
    'scripts/pre_qa_gate.py', 'scripts/run_pre_qa_exact_runtime.sh',
    'scripts/run_pre_qa_source_fallback.sh',
    '.github/workflows/stage0-tests.yml', A,
)
OFF = (
    'README.md', 'docs/ENVIRONMENT.md', 'docs/STAGE0_VALIDATION.md',
    '.github/workflows/stage0-tests.yml', 'scripts/run_pre_qa_exact_runtime.sh',
    'scripts/run_pre_qa_source_fallback.sh',
)
TF = ('data/raw/', 'data/normalized/', 'data/canonical/', 'data/derived/', 'research/', 'restricted/')
CF = TF + ('data/research/', 'data/restricted/')
SEC = re.compile(r'(^|/)(?:\.env(?:\.|$)|[^/]+\.(?:pem|key|p12|pfx)$|secrets?(?:\.|/|$))', re.I)
SHA40 = re.compile(r'^[0-9a-f]{40}$')


def sh(*a):
    p = subprocess.run(a, cwd=R, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(f"{' '.join(a)} -> {p.returncode}: {p.stderr}")
    return p.stdout.strip()


def lock(text):
    d, bad = {}, []
    for n, s in enumerate(text.splitlines(), 1):
        s = s.strip()
        if not s or s.startswith('#'):
            continue
        if not re.fullmatch(r'[A-Za-z0-9_.-]+==[^ <>=!~;]+', s):
            bad.append(f'lock line {n} not exact: {s}')
            continue
        k, v = s.split('==')
        k = k.lower().replace('_', '-')
        if k in d:
            bad.append(f'duplicate lock: {k}')
        d[k] = v
    return d, bad


def hist(text):
    h = '\n'.join(text.splitlines()[:12]).upper()
    return any(x in h for x in ('SUPERSEDED', 'HISTORICAL', 'SUPERSESSION'))


def forbid(p, pfx):
    p = p.removeprefix('./')
    return p.startswith(pfx) or bool(SEC.search(p))


def runtime_errors(version=None):
    version = tuple(version or sys.version_info[:3])
    return [] if version == EXPECTED_PYTHON else [f"Python != 3.13.16: {'.'.join(map(str, version))}"]


def git_identity_errors(expected_sha, expected_parent):
    e = []
    if not SHA40.fullmatch(expected_sha):
        e.append('expected SHA must be 40 lowercase hex characters')
    if not SHA40.fullmatch(expected_parent):
        e.append('expected parent must be 40 lowercase hex characters')
    if e:
        return e
    try:
        if sh('git', 'rev-parse', 'HEAD') != expected_sha:
            e.append('HEAD != expected SHA')
        if sh('git', 'rev-parse', 'HEAD^') != expected_parent:
            e.append('HEAD^ != expected parent')
    except RuntimeError as x:
        e.append(str(x))
    return e


def checks(sha, parent, architecture_revision):
    e = runtime_errors()
    e += git_identity_errors(sha, parent)
    for f in REQ:
        if not (R / f).is_file():
            e.append(f'missing: {f}')
    try:
        if sh('git', 'status', '--porcelain', '--untracked-files=all'):
            e.append('dirty working tree')
        sh('git', 'diff', '--check', parent, 'HEAD')
    except RuntimeError as x:
        e.append(str(x))
    if (R / '.python-version').read_text().strip() != '3.13.16':
        e.append('.python-version mismatch')
    try:
        p = tomllib.loads((R / 'pyproject.toml').read_text())
        if p['project']['requires-python'] != '==3.13.16':
            e.append('requires-python mismatch')
        if set(p['build-system']['requires']) != {'setuptools==80.9.0', 'wheel==0.45.1'}:
            e.append('build pins mismatch')
    except Exception as x:
        e.append(f'pyproject: {x}')
    got, bad = lock((R / 'requirements.lock').read_text())
    e += bad
    if got != L:
        e.append(f'lock set mismatch: {got}')
    for k, v in L.items():
        try:
            av = md.version(k)
        except md.PackageNotFoundError:
            e.append(f'not installed: {k}=={v}')
            continue
        if av != v:
            e.append(f'{k}={av}, expected {v}')
    src = (R / 'src').resolve()
    for x in filter(None, os.environ.get('PYTHONPATH', '').split(os.pathsep)):
        if Path(x).resolve() == src:
            e.append('PYTHONPATH points to src')
    try:
        import pro_adherence
        if not Path(pro_adherence.__file__).resolve().is_relative_to((R / 'src/pro_adherence').resolve()):
            e.append('package not imported from installed checkout')
    except Exception as x:
        e.append(f'import failed: {x}')
    for f in OFF:
        t = (R / f).read_text()
        if 'PYTHONPATH=src python' in t or 'PYTHONPATH: src' in t:
            e.append(f'official PYTHONPATH source-path command remains in {f}')
    for p in sorted((R / 'docs/handoffs').glob('*.md')):
        if p.relative_to(R).as_posix() != A and not hist(p.read_text()):
            e.append(f'unmarked historical handoff: {p.name}')
    for f in (
        'docs/STAGE0_CONTRACT_MIGRATION_2026-10-08.md',
        'docs/STAGE0_MODEL_IDENTITY_MIGRATION_2026-10-08.md',
        'docs/STAGE0_PROVENANCE.md', 'docs/STAGE0_STATUS.md',
    ):
        h = '\n'.join((R / f).read_text().splitlines()[:12]).upper()
        if not any(x in h for x in ('HISTORICAL', 'SUPERSEDED', 'OPERATIONAL STATUS')):
            e.append(f'status marker missing: {f}')
    try:
        for p in sh('git', 'ls-files').splitlines():
            if forbid(p, TF):
                e.append(f'forbidden tracked path: {p}')
        for p in sh('git', 'diff', '--name-only', parent, 'HEAD').splitlines():
            if forbid(p, CF):
                e.append(f'forbidden candidate path: {p}')
    except RuntimeError as x:
        e.append(str(x))
    t = (R / A).read_text()
    for s in (
        parent, f'TECHNICAL_ARCHITECTURE revision {architecture_revision}',
        '01_PROJECT_RULES v0.3', '07_STAGE_STATUS', 'PRE_QA_GATE',
    ):
        if s not in t:
            e.append(f'admission pin missing: {s}')
    t = (R / 'docs/ENVIRONMENT.md').read_text()
    for s in (
        'Python 3.13.16', 'requirements.lock', '--no-build-isolation --no-deps -e .',
        'network', 'UTF-8', 'Git', 'no secrets', '07_STAGE_STATUS',
        'linux/amd64', 'sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024',
        'f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d',
    ):
        if s not in t:
            e.append(f'environment assumption missing: {s}')
    return e


def gate():
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    runs = (
        (sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'),
        (sys.executable, '-m', 'pro_adherence.validate', 'contracts'),
        (sys.executable, '-m', 'pro_adherence.validate', 'corpus', 'contracts/manifests/empty_corpus.manifest.json'),
        (sys.executable, '-m', 'pro_adherence.validate', 'release', 'contracts/manifests/empty_release.manifest.json'),
        (sys.executable, '-m', 'pro_adherence.validate', 'lineage', 'contracts/manifests/minimal_lineage.example.json'),
        (sys.executable, '-m', 'pro_adherence.validate', 'boundary'),
        (sys.executable, '-m', 'pro_adherence.validate', 'stage0'),
        (sys.executable, 'scripts/stage0_mutation_audit.py'),
    )
    for a in runs:
        p = subprocess.run(a, cwd=R, env=env)
        print('[PASS]' if p.returncode == 0 else '[FAIL]', ' '.join(a), f'exit={p.returncode}')
        if p.returncode:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--expected-sha', required=True)
    ap.add_argument('--expected-parent', required=True)
    ap.add_argument('--architecture-revision', required=True)
    ap.add_argument('--static-only', action='store_true')
    a = ap.parse_args()
    e = checks(a.expected_sha, a.expected_parent, a.architecture_revision)
    if e:
        print('PRE_QA preflight: FAIL', file=sys.stderr)
        [print('-', x, file=sys.stderr) for x in e]
        return 1
    print('PRE_QA static checks: PASS')
    if not a.static_only and not gate():
        return 1
    print('PRE_QA machine-checkable evidence: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
