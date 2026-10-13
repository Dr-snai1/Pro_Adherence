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
PARENT = "c12135e06429b159fe0704eb13ef693a8cb92b37"
REPO = "Dr-snai1/Pro_Adherence-research-evidence"
REQUIRED = (
    "src/pro_adherence/pubmed_evidence.py",
    ".github/workflows/pubmed-evidence-manual.yml",
    "configs/pubmed/smoke.v1.json", "docs/PUBMED_EVIDENCE_RUNNER.md",
    "tests/test_pubmed_evidence.py", "tests/test_pubmed_evidence_boundary.py",
    "tests/test_pubmed_checkpoint_and_samples.py",
    "tests/test_pubmed_adm001.py", "tests/test_pubmed_paths.py",
    "tests/test_pubmed_esearch_state.py",
    "tests/test_pubmed_terminal_failures.py",
    "scripts/pre_qa_gate.py", "scripts/pre_qa_task0004.py",
    "tests/test_pre_qa_task0004.py", ".github/workflows/stage0-tests.yml",
    "scripts/run_pre_qa_exact_runtime.sh", "scripts/run_pre_qa_source_fallback.sh",
)
# Scoped atomic security replacement from integrated rev23 main; historical Stage 0 pin unchanged.
AFFECTED = (
    ".github/workflows/pubmed-evidence-manual.yml",
    "scripts/pre_qa_task0004.py",
    "tests/test_pre_qa_task0004.py",
    "docs/PUBMED_EVIDENCE_RUNNER.md",
)
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

def _named_step(job, name):
    m = re.search(r"(?m)^      - name: " + re.escape(name) + r"\s*$", job)
    if m is None:
        return ""
    tail = job[m.end():]
    nxt = re.search(r"(?m)^      - (?:name:|uses:)", tail)
    return tail[:nxt.start()] if nxt else tail

def security_workflow_errors(text, writer, verifier):
    """Structural fail-closed security contract for TASK-0016."""
    errors = []
    retrieve = _named_step(writer, "Retrieve to isolated runner temporary storage")
    if (text.count("secrets.NCBI_EMAIL") != 1 or "vars.NCBI_EMAIL" in text
            or not re.search(r"(?m)^          NCBI_EMAIL: [$][{][{] secrets[.]NCBI_EMAIL [}][}]\s*$", retrieve)):
        errors.append("NCBI_EMAIL must be sourced exactly from research-pubmed Environment secret")
    if (not re.search(r"(?m)^          NCBI_TOOL: [$][{][{] vars[.]NCBI_TOOL [}][}]\s*$", retrieve)
            or not re.search(r"(?m)^          NCBI_API_KEY: [$][{][{] secrets[.]NCBI_API_KEY [}][}]\s*$", retrieve)):
        errors.append("NCBI_TOOL and optional NCBI_API_KEY configuration contract missing")
    if re.search(
        r"(?im)^\s*(?:echo\b|printf\b|print\s*\(|printenv\b|set\s+-x\b|bash\s+-x\b)[^\n]*NCBI_EMAIL\b"
        r"|^.*(?:NCBI_EMAIL[^\n]*GITHUB_OUTPUT|GITHUB_OUTPUT[^\n]*NCBI_EMAIL)",
        text):
        errors.append("public log or GitHub output cannot contain NCBI_EMAIL")
    if re.search(r"(?m)^\s{10,}(?:env|printenv)(?:\s|$)|^\s{10,}(?:set|bash)\s+-x(?:\s|$)", text):
        errors.append("environment dump or shell tracing forbidden")
    # Match an active shell control-flow sequence, not a collection of keywords.
    probe = (
        '          git clone --quiet "git@github.com:$REPOSITORY.git" "$RUNNER_TEMP/pubmed-permission-probe" >/dev/null 2>&1\n'
        '          git -C "$RUNNER_TEMP/pubmed-permission-probe" checkout --quiet --detach "$EVIDENCE_COMMIT"\n'
        '          if git -C "$RUNNER_TEMP/pubmed-permission-probe" push --dry-run "git@github.com:$REPOSITORY.git" HEAD:refs/heads/__readback_permission_probe__ >/dev/null 2>&1; then\n'
        "            echo 'read-only evidence credential unexpectedly has write capability' >&2\n"
        '            exit 1\n'
        '          fi\n'
    )
    position = verifier.find(probe)
    readback = _named_step(verifier, "Independent read-only clone of exact evidence commit")
    if (position < 0 or verifier.count('git -C "$RUNNER_TEMP/pubmed-permission-probe" push') != 1
            or not (verifier.find("export GIT_SSH_COMMAND=") < position < verifier.find('result='))
            or probe not in readback):
        errors.append("fail-closed non-mutating READ-key dry-run probe before exact readback is mandatory")
    for line in verifier.splitlines():
        if re.search(r"\bgit\b[^\n]*\bpush\b", line) and line.strip() != probe.splitlines()[2].strip():
            errors.append("unexpected verifier git push")
            break
    return errors

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
    if ("--allow-incomplete" not in verifier
            or "Durable terminal failure evidence verified; this run is not resumable." not in verifier
            or "Durable resumable incomplete checkpoint verified; re-run with matching resume_id." not in verifier
            or verifier.index("readback_flag") > verifier.index("Durable terminal failure evidence verified")
            or "Fail if source retrieval remained incomplete" in writer):
        errors.append("D1 post-write independent readback and truthful failure messaging absent")
    errors += security_workflow_errors(text, writer, verifier)
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
    adm = (root / "tests/test_pubmed_adm001.py").read_text()
    regression_names = (
        "test_failed_xml_attempts_survive_durable_checkpoint_retry_and_final",
        "test_pre_response_efetch_outage_has_no_fabricated_raw_and_resumes",
        "test_multi_query_unstarted_identity_git_resume_and_hash_before_network",
        "test_completed_query_missing_is_not_an_unstarted_query",
        "test_incomplete_state_metadata_self_rehash_cannot_forge_completion",
        "test_raw_esearch_tamper_with_rehashed_inventory_root_is_rejected",
        "test_zero_result_sample_is_final_without_efetch",
    )
    if any("def " + name + "(" not in adm for name in regression_names):
        errors.append("missing executable ADM-001 class regressions")
    paths = (root / "tests/test_pubmed_paths.py").read_text()
    required_paths = (
        "test_pairwise_role_namespace_injectivity",
        "test_collision_shaped_multi_query_final_and_strict_verify",
        "test_collision_shaped_git_checkpoint_resume_and_readback",
        "test_noncanonical_role_metadata_rejected_even_after_rehash",
        "test_unsafe_spec_rejected_before_network",
    )
    if any("def " + test + "(" not in paths for test in required_paths):
        errors.append("missing P2-001 whole-class executable regressions")
    for helper in ("query_path", "union_path", "leaf_path", "sample_path",
                   "esearch_raw_path", "efetch_raw_path", "semantic_paths"):
        if helper not in src:
            errors.append("canonical role-path helper absent: " + helper)
    for statement in ("failed_checkpointable", "not_started", "checked_sample",
                      "result_ids_sha256", "efetch_raw_path"):
        if statement not in src:
            errors.append("state/raw-source contract missing: " + statement)
    esearch = (root / "tests/test_pubmed_esearch_state.py").read_text()
    for name in ("test_normal_zero_and_full_module_self_rehashed_role_swap",
                 "test_partition_count_ids_chronology_and_self_rehashed_swap",
                 "test_rejected_count_raw_checkpoint_resume_and_pre_network_validation",
                 "test_rejected_ids_raw_checkpoint_resume_and_tampered_prefix"):
        if "def " + name + "(" not in esearch:
            errors.append("missing P2-002 executable test: " + name)
    if "esearch_expected_trace" not in src:
        errors.append("missing deterministic ESearch state machine")
    terminal = (root / "tests/test_pubmed_terminal_failures.py").read_text()
    for name in ("test_unsplittable_single_day_durable_git_readback_nonresume",
                 "test_completed_frontier_source_mismatch_durable",
                 "test_cross_leaf_duplicate_durable",
                 "test_forged_terminal_on_pending_evidence",
                 "test_forged_resumable_on_terminal_evidence",
                 "test_resumable_rejected_count_ids_malformed",
                 "test_terminal_run_id_immutable",
                 "test_workflow_readback_before_failure_message"):
        if "def " + name + "(" not in terminal:
            errors.append("missing D1 executable regression: " + name)
    if any(token not in src for token in ("failed_terminal", "failure_disposition",
                                           "unsplittable_single_day_partition",
                                           "source_count_mismatch", "cross_leaf_duplicate")):
        errors.append("missing terminal-state semantic implementation")
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
              "infrastructure acceptance", "HOFF-0019", "failed_checkpointable",
              "not_started", "raw-to-derived", "no EFetch", "no sample XML",
              "immutable attempt", "before the first request", "role-separated",
              "A-00000", "no operational migration", "failed_terminal",
               "unsplittable_single_day_partition", "source_count_mismatch",
               "cross_leaf_duplicate", "not resumable"):

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
    if not errors:
        # Executable ADM-001 documentation/behavior contract, even with --static-only.
        # This is a focused test, not static keyword-only admission evidence.
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_pubmed_adm001.py", "-v"], cwd=R, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        # P2-001 must execute as part of admission even with --static-only.
        collision = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_pubmed_paths.py", "-v"], cwd=R, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        semantic = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_pubmed_esearch_state.py", "-v"], cwd=R, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        terminal = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_pubmed_terminal_failures.py", "-v"], cwd=R, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        if terminal.returncode:
            errors.append("D1 executable terminal failure regressions failed")
            print(terminal.stdout[-3000:], file=sys.stderr)
            print(terminal.stderr[-7000:], file=sys.stderr)
        if semantic.returncode:
            errors.append("P2-002 executable semantic state-machine regressions failed")
            print(semantic.stdout[-3000:], file=sys.stderr)
            print(semantic.stderr[-7000:], file=sys.stderr)
        if collision.returncode:
            errors.append("P2-001 executable collision regressions failed")
            print(collision.stdout[-3000:], file=sys.stderr)
            print(collision.stderr[-7000:], file=sys.stderr)
        if r.returncode:
            errors.append("ADM-001 executable regressions failed")
            print(r.stdout[-3000:], file=sys.stderr)
            print(r.stderr[-7000:], file=sys.stderr)
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
