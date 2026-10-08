"""Independent semantic mutation audit for Stage 0 validator gates."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pro_adherence import validate as v

CTX = v.SchemaContext.from_repo(ROOT)


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def uid(n):
    return f"018f0c50-7b1d-7cc3-8a5b-{n:012d}"


def set_hash(manifest):
    manifest["manifest_hash"] = v.recompute_manifest_hash(manifest)


def public_access():
    return {
        "access_class": "public",
        "license_class": "fixture",
        "license_status": "confirmed",
        "license_evidence_ref": "fixture",
        "publication_permissions": {"metadata": "allow", "raw_text": "deny", "derived": "allow"},
    }


def promoted_fixture():
    lineage = load("contracts/manifests/minimal_lineage.example.json")
    artifact = lineage["artifacts"][-1]
    artifact["access_license"] = public_access()
    release_id, report_id, event_id = uid(950), uid(951), uid(952)
    release = {
        "manifest_version": "1.0.0", "release_id": release_id, "status": "promoted",
        "corpus_release_id": lineage["corpus_release_ids"][0],
        "artifacts": [{
            "artifact_id": artifact["artifact_id"], "artifact_type": artifact["artifact_type"],
            "content_hash": artifact["content_hash"], "schema_version": artifact["schema_version"],
            "role": "result", "public_path": "data/result.json",
            "publication_permission_basis": "derived", "access_license": copy.deepcopy(artifact["access_license"]),
        }],
        "promotion_event_ids": [event_id], "manifest_hash": "",
        "created_at": "2026-10-08T01:00:00Z", "superseded_by": None,
    }
    set_hash(release)
    report = {
        "record_type": "quality_report", "quality_report_id": report_id,
        "subject_artifact_id": artifact["artifact_id"], "status": "pass",
        "checks": [{"check_id": "fixture", "status": "pass"}],
        "created_at": "2026-10-08T00:59:00Z",
    }
    event = {
        "record_type": "promotion_event", "promotion_event_id": event_id,
        "artifact_ids": [artifact["artifact_id"]], "quality_report_ids": [report_id],
        "decision": "promoted", "target_release_id": release_id,
        "created_at": "2026-10-08T01:00:00Z",
    }
    corpus = load("contracts/manifests/empty_corpus.manifest.json")
    corpus["corpus_release_id"] = lineage["corpus_release_ids"][0]
    set_hash(corpus)
    return lineage, release, corpus, report, event


def release_errors(
    lineage, release, corpus, report, event, events=None, reports=None,
    lineage_artifact_ids=None,
):
    catalog = v.catalog_from_bundle(lineage)
    return v.validate_release_manifest(
        release, ctx=CTX, artifacts=catalog.artifacts,
        corpus_manifests={corpus["corpus_release_id"]: corpus},
        promotion_events=events if events is not None else {event["promotion_event_id"]: event},
        quality_reports=reports if reports is not None else {report["quality_report_id"]: report},
        run_outputs=catalog.run_outputs,
        lineage_artifact_ids=(
            set(lineage_artifact_ids)
            if lineage_artifact_ids is not None
            else {item["artifact_id"] for item in release.get("artifacts", [])}
        ),
    )


def add_second_direct_output(lineage, release, event):
    artifact = copy.deepcopy(lineage["artifacts"][-1])
    artifact["artifact_id"] = uid(970)
    artifact["uri"] = "derived/synthetic/second-output.json"
    artifact["content_hash"] = "9" * 64
    artifact["access_license"] = public_access()
    lineage["artifacts"].append(artifact)

    binding = copy.deepcopy(lineage["run_outputs"][0])
    binding["artifact_id"] = artifact["artifact_id"]
    binding["role"] = "result_b"
    lineage["run_outputs"].append(binding)

    item = copy.deepcopy(release["artifacts"][0])
    item["artifact_id"] = artifact["artifact_id"]
    item["content_hash"] = artifact["content_hash"]
    item["public_path"] = "data/result-b.json"
    release["artifacts"].append(item)
    event["artifact_ids"].append(artifact["artifact_id"])
    set_hash(release)
    return artifact["artifact_id"]


checks = []

bundle = load("contracts/manifests/minimal_lineage.example.json")
x = copy.deepcopy(bundle)
x["run_inputs"][0]["artifact_id"] = uid(960)
checks.append(("dangling ref", v.validate_lineage(x, CTX)))

x = copy.deepcopy(bundle)
run = copy.deepcopy(x["runs"][0]); run["run_id"] = uid(961); x["runs"].append(run)
out = copy.deepcopy(x["run_outputs"][0]); out["run_id"] = run["run_id"]; x["run_outputs"].append(out)
checks.append(("duplicate producer", v.validate_lineage(x, CTX)))

corpus = load("contracts/manifests/empty_corpus.manifest.json")
x = copy.deepcopy(corpus); x["manifest_hash"] = "0" * 64
checks.append(("wrong manifest hash", v.validate_corpus_manifest(x, root=ROOT, ctx=CTX, artifacts={})))

x = copy.deepcopy(corpus); x["inclusion_policy"]["content_hash"] = "0" * 64; set_hash(x)
checks.append(("wrong policy hash", v.validate_corpus_manifest(x, root=ROOT, ctx=CTX, artifacts={})))

x = copy.deepcopy(corpus); x["article_count"] = 1; set_hash(x)
checks.append(("wrong article count", v.validate_corpus_manifest(x, root=ROOT, ctx=CTX, artifacts={})))

lineage, release, rel_corpus, report, event = promoted_fixture()
x = copy.deepcopy(release); x["artifacts"][0]["content_hash"] = "1" * 64; set_hash(x)
checks.append(("wrong artifact hash", release_errors(lineage, x, rel_corpus, report, event)))

checks.append(("promotion without evidence", release_errors(lineage, release, rel_corpus, report, event, events={})))

catalog = v.catalog_from_bundle(lineage)
checks.append(("promotion without complete lineage", v.validate_release_manifest(
    release, ctx=CTX, artifacts=catalog.artifacts,
    corpus_manifests={rel_corpus["corpus_release_id"]: rel_corpus},
    promotion_events={event["promotion_event_id"]: event},
    quality_reports={report["quality_report_id"]: report},
    run_outputs=catalog.run_outputs,
    lineage_artifact_ids=set(),
)))

bad_event = copy.deepcopy(event); bad_event["target_release_id"] = uid(962)
checks.append(("wrong promotion target", release_errors(lineage, release, rel_corpus, report, bad_event)))

restricted = copy.deepcopy(lineage)
restricted["artifacts"][-1]["access_license"]["access_class"] = "restricted-license"
checks.append(("restricted public artifact", release_errors(restricted, release, rel_corpus, report, event)))

mismatch = copy.deepcopy(lineage)
mismatch["artifacts"][-1]["corpus_release_id"] = uid(963)
checks.append(("corpus mismatch", release_errors(mismatch, release, rel_corpus, report, event)))

lineage, release, rel_corpus, report, event = promoted_fixture()
report["status"] = "warn"; report["checks"][0]["status"] = "warn"
checks.append(("PASS -> WARN", release_errors(lineage, release, rel_corpus, report, event)))

lineage, release, rel_corpus, report, event = promoted_fixture()
report["status"] = "fail"; report["checks"][0]["status"] = "fail"
checks.append(("PASS -> FAIL", release_errors(lineage, release, rel_corpus, report, event)))

lineage, release, rel_corpus, report, event = promoted_fixture()
report["checks"][0]["status"] = "warn"
checks.append(("declared PASS + WARN check", release_errors(lineage, release, rel_corpus, report, event)))

lineage, release, rel_corpus, report, event = promoted_fixture()
report["checks"][0]["status"] = "fail"
checks.append(("declared PASS + FAIL check", release_errors(lineage, release, rel_corpus, report, event)))

lineage, release, rel_corpus, report, event = promoted_fixture()
report["subject_artifact_id"] = uid(964)
checks.append(("unrelated quality report", release_errors(lineage, release, rel_corpus, report, event)))

lineage, release, rel_corpus, report, event = promoted_fixture()
report.pop("subject_artifact_id")
report["subject_run_id"] = lineage["runs"][0]["run_id"]
lineage["run_outputs"] = []
checks.append(("remove direct run_output relation", release_errors(lineage, release, rel_corpus, report, event)))

lineage, release, rel_corpus, report, event = promoted_fixture()
add_second_direct_output(lineage, release, event)
checks.append(("remove one artifact coverage", release_errors(lineage, release, rel_corpus, report, event)))

lineage, release, rel_corpus, report, event = promoted_fixture()
extra_report = copy.deepcopy(report)
extra_report["quality_report_id"] = uid(965)
extra_report["subject_artifact_id"] = uid(966)
event["quality_report_ids"].append(extra_report["quality_report_id"])
checks.append(("add unrelated PASS to evidence set", release_errors(
    lineage, release, rel_corpus, report, event,
    reports={report["quality_report_id"]: report, extra_report["quality_report_id"]: extra_report},
)))

lineage, release, rel_corpus, report, event = promoted_fixture()
event["decision"] = "rejected"
checks.append(("replace promoted event with rejected", release_errors(lineage, release, rel_corpus, report, event)))

lineage, release, rel_corpus, report, event = promoted_fixture()
release["promotion_event_ids"] = []
set_hash(release)
checks.append(("remove release-level event coverage", release_errors(lineage, release, rel_corpus, report, event)))


failed = []
for name, errors in checks:
    if not errors:
        failed.append(name)
    else:
        print(f"EXPECTED_FAIL {name}: {errors[0]}")

chain = v.reconstruct_lineage(bundle, bundle["root_output_artifact_id"])
expected = {
    "root_output_artifact_id": bundle["root_output_artifact_id"],
    "root_producing_run_id": bundle["runs"][0]["run_id"],
    "direct_input_artifact_ids": [bundle["run_inputs"][0]["artifact_id"]],
    "ancestor_artifact_ids": sorted([bundle["run_inputs"][0]["artifact_id"], bundle["source_fetches"][0]["raw_artifact_id"]]),
    "descendant_artifact_ids": [],
    "direct_child_artifact_ids": [],
    "source_fetch_ids": [bundle["source_fetches"][0]["source_fetch_id"]],
    "corpus_release_ids": [bundle["corpus_release_ids"][0]],
    "code_ref_ids": [bundle["code_refs"][0]["code_ref_id"]],
    "config_ref_ids": [bundle["config_refs"][0]["config_ref_id"]],
    "model_ref_ids": [bundle["model_refs"][0]["model_ref_id"]],
    "environment_ref_ids": [bundle["environment_refs"][0]["environment_ref_id"]],
}
if chain != expected:
    failed.append("lineage exact chain")
    print("LINEAGE_MISMATCH")
    print(json.dumps({"expected": expected, "actual": chain}, indent=2, sort_keys=True))
else:
    print("PASS lineage exact chain")

if failed:
    print("AUDIT FAIL:", ", ".join(failed))
    raise SystemExit(1)

decision_failures = []


def record_decision(name, expected_valid, errors):
    actual_valid = not errors
    print(
        f"DECISION {name}: expected={'VALID' if expected_valid else 'INVALID'} "
        f"actual={'VALID' if actual_valid else 'INVALID'}"
    )
    if actual_valid != expected_valid:
        decision_failures.append(name)


lineage, release, rel_corpus, report, event = promoted_fixture()
record_decision("applicable PASS", True, release_errors(lineage, release, rel_corpus, report, event))

lineage, release, rel_corpus, report, event = promoted_fixture()
report["status"] = "warn"; report["checks"][0]["status"] = "warn"
record_decision("WARN", False, release_errors(lineage, release, rel_corpus, report, event))

lineage, release, rel_corpus, report, event = promoted_fixture()
report["status"] = "fail"; report["checks"][0]["status"] = "fail"
record_decision("FAIL", False, release_errors(lineage, release, rel_corpus, report, event))

lineage, release, rel_corpus, report, event = promoted_fixture()
warn = copy.deepcopy(report); warn["quality_report_id"] = uid(980); warn["status"] = "warn"; warn["checks"][0]["status"] = "warn"
event["quality_report_ids"].append(warn["quality_report_id"])
record_decision("PASS + WARN", False, release_errors(
    lineage, release, rel_corpus, report, event,
    reports={report["quality_report_id"]: report, warn["quality_report_id"]: warn},
))

lineage, release, rel_corpus, report, event = promoted_fixture()
fail = copy.deepcopy(report); fail["quality_report_id"] = uid(981); fail["status"] = "fail"; fail["checks"][0]["status"] = "fail"
event["quality_report_ids"].append(fail["quality_report_id"])
record_decision("PASS + FAIL", False, release_errors(
    lineage, release, rel_corpus, report, event,
    reports={report["quality_report_id"]: report, fail["quality_report_id"]: fail},
))

lineage, release, rel_corpus, report, event = promoted_fixture()
report["subject_artifact_id"] = uid(982)
record_decision("unrelated PASS", False, release_errors(lineage, release, rel_corpus, report, event))

lineage, release, rel_corpus, report, event = promoted_fixture()
report.pop("subject_artifact_id"); report["subject_run_id"] = lineage["runs"][0]["run_id"]
record_decision("run PASS -> direct output", True, release_errors(lineage, release, rel_corpus, report, event))

lineage, release, rel_corpus, report, event = promoted_fixture()
root_artifact = lineage["artifacts"][-1]
child = copy.deepcopy(root_artifact)
child["artifact_id"] = uid(983); child["content_hash"] = "7" * 64; child["uri"] = "derived/synthetic/descendant.json"
lineage["artifacts"].append(child)
child_run = copy.deepcopy(lineage["runs"][0]); child_run["run_id"] = uid(984)
lineage["runs"].append(child_run)
lineage["run_inputs"].append({"record_type": "run_input", "run_id": child_run["run_id"], "artifact_id": root_artifact["artifact_id"], "role": "input"})
lineage["run_outputs"].append({"record_type": "run_output", "run_id": child_run["run_id"], "artifact_id": child["artifact_id"], "role": "result"})
release["artifacts"][0]["artifact_id"] = child["artifact_id"]
release["artifacts"][0]["content_hash"] = child["content_hash"]
release["artifacts"][0]["public_path"] = "data/descendant.json"
event["artifact_ids"] = [child["artifact_id"]]
report.pop("subject_artifact_id"); report["subject_run_id"] = lineage["runs"][0]["run_id"]
set_hash(release)
record_decision("run PASS -> descendant only", False, release_errors(lineage, release, rel_corpus, report, event))

lineage, release, rel_corpus, report, event = promoted_fixture()
add_second_direct_output(lineage, release, event)
record_decision("artifact without coverage", False, release_errors(lineage, release, rel_corpus, report, event))

lineage, release, rel_corpus, report, event = promoted_fixture()
event["decision"] = "rejected"
record_decision("rejected event", False, release_errors(lineage, release, rel_corpus, report, event))

lineage, release, rel_corpus, report, event = promoted_fixture()
report["checks"][0]["status"] = "warn"
record_decision("inconsistent report status", False, release_errors(lineage, release, rel_corpus, report, event))

lineage, release, rel_corpus, report, event = promoted_fixture()
add_second_direct_output(lineage, release, event)
event["artifact_ids"] = [release["artifacts"][0]["artifact_id"]]
record_decision("release union coverage", False, release_errors(lineage, release, rel_corpus, report, event))

if decision_failures:
    print("DECISION AUDIT FAIL:", ", ".join(decision_failures))
    raise SystemExit(1)
print(f"AUDIT PASS: {len(checks)} expected failures + exact lineage chain; decision matrix 12/12")
