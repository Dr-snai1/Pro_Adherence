#!/usr/bin/env python3
"""TASK-0004 implementation PRE_QA / TECHNICAL_ARCHITECTURE revision 23.
NOT an NCBI, private evidence, or owner-local backup acceptance verdict.
"""
import argparse
import importlib.metadata as md
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib

R = Path(__file__).resolve().parents[1]
PARENT = "c0917885d565348df47417ba34516e79d2e049c9"
REPO = "Dr-snai1/Pro_Adherence-research-evidence"
REQUIRED = (
    "src/pro_adherence/pubmed_evidence.py",
    ".github/workflows/pubmed-evidence-manual.yml",
    "configs/pubmed/smoke.v1.json", "docs/PUBMED_EVIDENCE_RUNNER.md",
    "tests/test_pubmed_evidence.py", "tests/test_pubmed_evidence_boundary.py",
    "tests/test_pubmed_checkpoint_and_samples.py",
    "scripts/pre_qa_gate.py", "scripts/pre_qa_task0004.py",
    "tests/test_pre_qa_task0004.py", ".github/workflows/stage0-tests.yml",
    "scripts/run_pre_qa_exact_runtime.sh", "scripts/run_pre_qa_source_fallback.sh",
)
AFFECTED = REQUIRED[:7] + REQUIRED[8:11]
LOCK = {
    "attrs": "25.4.0", "jsonschema": "4.26.0",
    "jsonschema-specifications": "2025.9.1", "pip": "25.2",
    "referencing": "0.36.2", "rpds-py": "0.27.1",
    "setuptools": "80.9.0", "wheel": "0.45.1",
}
BLOCKED_PATHS = (
    "data/raw/", "data/normalized/", "data/canonical/", "data/derived/",
    "data/research/", "data/restricted/", "research/", "restricted/",
    "public/evidence/", "serving/evidence/",
)
SECRET_PATH = re.compile(r"(^|/)(?:\.env(?:\.|$)|secrets?(?:\.|/|$)|[^/]+\.(?:pem|key|p12|pfx)$|id_(?:rsa|ed25519)$)", re.I)
STATUS_PATTERNS = (
    re.compile(r"\bStage\s*[01]\s*(?:=|—|-|:)\s*(?:OPEN|CLOSED|PASS|FAIL|RELEASE-READY)\b", re.I),
    re.compile(r"\bQA-S0-\d+\s*(?:=|—|-|:)\s*(?:OPEN|CLOSED|PASS|FAIL|PENDING)\b", re.I),
    re.compile(r"\b(?:independent\s+QA\s+(?:is\s+)?pending|QA\s+pending)\b", re.I),
)

def sh(*args):
    p = subprocess.run(args, cwd=R, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError("command failed: " + " ".join(args) + ": " + p.stderr.strip())
    return p.stdout.strip()

def identity_errors(sha, parent, git=sh):
    errors = []
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        errors.append("invalid exact candidate SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", parent) or parent != PARENT:
        errors.append("candidate parent must be accepted c0917885 baseline")
    if errors:
        return errors
    try:
        if git("git", "rev-parse", "HEAD") != sha:
            errors.append("HEAD != exact SHA")
        if git("git", "rev-parse", "HEAD^") != parent:
            errors.append("HEAD^ != exact parent")
    except RuntimeError as exc:
        errors.append(str(exc))
    return errors

def revision_errors(revision):
    return [] if str(revision) == "23" else ["pinned TECHNICAL_ARCHITECTURE revision must be 23"]

def file_errors(root=R):
    return ["missing: " + p for p in REQUIRED if not (root / p).is_file()]

def forbid(path):
    path = path.replace("\\", "/")
    return (path.startswith("/") or any(seg in ("", ".", "..") for seg in path.split("/"))
            or any(path == x.rstrip("/") or path.startswith(x) for x in BLOCKED_PATHS)
            or bool(SECRET_PATH.search(path)))

def diff_errors(paths):
    return ([f"forbidden candidate path: {p}" for p in paths if forbid(p)]
            + [f"missing atomic affected scope: {p}" for p in AFFECTED if p not in paths])

def block(text, name):
    match = re.search(r"(?m)^" + re.escape(name) + r":([^\n]*)\n", text)
    if not match or match.group(1).strip():
        return ""
    tail = text[match.end():]
    end = re.search(r"(?m)^[A-Za-z][A-Za-z0-9_-]*:", tail)
    return tail[:end.start()] if end else tail

def workflow_errors(text):
    errors = []
    trigger = block(text, "on")
    names = re.findall(r"(?m)^  ([A-Za-z_][A-Za-z_0-9-]*):", trigger)
    if names != ["workflow_dispatch"]:
        errors.append("trigger must be workflow_dispatch only")
    perms = [line.strip() for line in block(text, "permissions").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if perms != ["contents: read"]:
        errors.append("public workflow permissions must equal contents: read")
    jobs = block(text, "jobs")
    headers = list(re.finditer(r"(?m)^  ([A-Za-z_][A-Za-z_0-9-]*):\s*$", jobs))
    if [m.group(1) for m in headers] != ["evidence-writer", "independent-readback"]:
        return errors + ["requires exactly writer and independent-readback jobs"]
    writer = jobs[headers[0].end():headers[1].start()]
    verifier = jobs[headers[1].end():]
    if "default: smoke" not in trigger or "options: [smoke, full]" not in trigger:
        errors.append("default mode must be smoke")
    if text.count("environment: research-pubmed") != 2:
        errors.append("both jobs must use research-pubmed environment")
    if "secrets.RESEARCH_EVIDENCE_WRITE_SSH_KEY" not in writer or "secrets.RESEARCH_EVIDENCE_READ_SSH_KEY" in writer:
        errors.append("writer SSH slot wrong")
    if "secrets.RESEARCH_EVIDENCE_READ_SSH_KEY" not in verifier or "secrets.RESEARCH_EVIDENCE_WRITE_SSH_KEY" in verifier:
        errors.append("read-only SSH slot wrong")
    if "needs: evidence-writer" not in verifier:
        errors.append("readback must depend on writer job")
    for identity in ("commit", "root", "task", "run"):
        if "needs.evidence-writer.outputs." + identity not in verifier:
            errors.append("independent readback must consume exact writer " + identity)
    if "readback " not in verifier or "--commit \"$EVIDENCE_COMMIT\"" not in verifier:
        errors.append("no independent exact commit readback command")
    if "result['root_hash'] != os.environ['EXPECTED_ROOT']" not in verifier:
        errors.append("readback root comparison missing")
    if text.count("test \"$REPOSITORY\" = '" + REPO + "'") < 3 or "vars.RESEARCH_EVIDENCE_REPOSITORY" not in text:
        errors.append("private approved evidence destination not fixed")
    if text.count("ref: $" + "{{ github.sha }}") != 2 or text.count("persist-credentials: false") != 2:
        errors.append("pinned public checkout/credential boundary missing")
    if any(x in text for x in ("actions/upload-artifact", "actions/deploy-pages", "git push --force", "git add .")):
        errors.append("public output, Pages, or force-write forbidden")
    if "TECHNICAL_ARCHITECTURE revision 23" not in text:
        errors.append("workflow architecture revision absent")
    return errors

def status_errors(path, content):
    return [f"{path}: stale current-status claim: {m.group(0)}"
            for rule in STATUS_PATTERNS for m in rule.finditer(content)]

def environment_errors(root=R):
    errors = []
    if sys.version_info[:3] != (3, 13, 16):
        errors.append("exact Python 3.13.16 required")
    if (root / ".python-version").read_text().strip() != "3.13.16":
        errors.append(".python-version mismatch")
    spec = tomllib.loads((root / "pyproject.toml").read_text())
    if spec["project"]["requires-python"] != "==3.13.16":
        errors.append("requires-python mismatch")
    if set(spec["build-system"]["requires"]) != {"setuptools==80.9.0", "wheel==0.45.1"}:
        errors.append("build lock mismatch")
    pins = {}
    for line in (root / "requirements.lock").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]+==[^ <>=!~;]+", line):
            errors.append("non-exact lock: " + line)
        else:
            k, v = line.split("==")
            pins[k.lower().replace("_", "-")] = v
    if pins != LOCK:
        errors.append("lock set mismatch")
    for k, v in LOCK.items():
        try:
            if md.version(k) != v:
                errors.append("installed lock mismatch: " + k)
        except md.PackageNotFoundError:
            errors.append("missing installed lock: " + k)
    if any(Path(p).resolve() == (root / "src").resolve()
           for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p):
        errors.append("hidden PYTHONPATH=src")
    try:
        import pro_adherence
        if not Path(pro_adherence.__file__).resolve().is_relative_to((root / "src/pro_adherence").resolve()):
            errors.append("installed package not from checkout")
    except ImportError as exc:
        errors.append("package import: " + str(exc))
    return errors

def runner_errors(root=R):
    src = (root / "src/pro_adherence/pubmed_evidence.py").read_text()
    focused = "\n".join((root / path).read_text() for path in REQUIRED if path.startswith("tests/"))
    groups = (
        ("exact query and deterministic identity", ("read_spec", "canonical", "run_id", "query")),
        ("POST ESearch and EFetch", ("method=\"POST\"", "esearch", "efetch")),
        ("rate limiter and retries", ("0.36", "35", "429", "503")),
        ("fail-closed partition/reconciliation", ("10000", "plan_spans", "numeric_pmids", "reconciliation")),
        ("raw and deterministic package hashes", ("write_raw", "write_manifest", "package_root_sha256")),
        ("package and evidence repository guard", ("MAX_PACKAGE", "MAX_REPOSITORY")),
        ("append-only/private evidence and readback", ("git_write", "clone_readback", "backup")),
        ("strict evidence/checkpoint", ("strict_path", "prepare_resume", "verify")),
    )
    errors = ["runner static contract missing: " + label for label, tokens in groups
              if any(token not in src for token in tokens)]
    if "test_exact_query_preserved_and_raw_bytes" not in focused or "test_local_git_write_fresh_readback_and_backup" not in focused:
        errors.append("missing independent offline behavioral tests")
    return errors

def checks(sha, parent, revision):
    errors = identity_errors(sha, parent) + revision_errors(revision) + file_errors()
    if errors:
        return errors
    try:
        if sh("git", "status", "--porcelain", "--untracked-files=all"):
            errors.append("dirty Git tree")
        sh("git", "diff", "--check", parent, "HEAD")
        changed = sh("git", "diff", "--name-only", parent, "HEAD").splitlines()
        errors += diff_errors(changed)
    except RuntimeError as exc:
        errors.append(str(exc))
        changed = []
    errors += environment_errors()
    errors += workflow_errors((R / ".github/workflows/pubmed-evidence-manual.yml").read_text())
    errors += runner_errors()
    smoke = json.loads((R / "configs/pubmed/smoke.v1.json").read_text())
    if smoke.get("schema") != "pubmed-run-spec/v1" or smoke.get("task_id") != "TASK-0004" or not str(smoke.get("query_artifact", "")).startswith("infra-smoke") or len(smoke.get("queries", {})) != 1:
        errors.append("smoke spec must remain infrastructure-only")
    for path in changed:
        if path.startswith("docs/") and path.endswith(".md") and (R / path).is_file():
            errors += status_errors(path, (R / path).read_text())
    docs = (R / "docs/PUBMED_EVIDENCE_RUNNER.md").read_text()
    for s in ("revision 23", "revision 22", "scripts/pre_qa_task0004.py", "07_STAGE_STATUS",
              "infrastructure acceptance", "HOFF-0019"):
        if s not in docs:
            errors.append("missing candidate documentation: " + s)
    ci = (R / ".github/workflows/stage0-tests.yml").read_text()
    oci = (R / "scripts/run_pre_qa_exact_runtime.sh").read_text()
    if "--architecture-revision 22" not in ci or "--architecture-revision 23" not in ci or "scripts/pre_qa_task0004.py" not in ci or "--task0004-revision 23" not in ci:
        errors.append("CI must run both historical rev22 and candidate rev23")
    if "TASK0004_REVISION" not in oci or "scripts/pre_qa_task0004.py" not in oci:
        errors.append("pinned OCI must run TASK-0004 candidate admission")
    if "HISTORICAL_STAGE0_PARENT" not in (R / "scripts/pre_qa_gate.py").read_text():
        errors.append("historical Stage 0 pin missing")
    return errors

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected-sha", required=True)
    ap.add_argument("--expected-parent", required=True)
    ap.add_argument("--architecture-revision", required=True)
    ap.add_argument("--static-only", action="store_true")
    args = ap.parse_args()
    errors = checks(args.expected_sha, args.expected_parent, args.architecture_revision)
    if errors:
        print("TASK-0004 IMPLEMENTATION PRE_QA revision 23: FAIL", file=sys.stderr)
        for issue in errors:
            print("-", issue, file=sys.stderr)
        return 1
    if not args.static_only:
        p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
                           cwd=R, env={k:v for k,v in os.environ.items() if k != "PYTHONPATH"})
        if p.returncode:
            return p.returncode
    print("TASK-0004 IMPLEMENTATION PRE_QA revision 23: PASS")
    print("INFRASTRUCTURE ACCEPTANCE: BLOCKED pending HOFF-0019 provisioning, default-branch "
          "workflow, real NCBI smoke, private durable commit/root/counts, fresh read-only "
          "readback and independent owner-local hash-verified backup")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
