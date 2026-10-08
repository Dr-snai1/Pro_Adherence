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


def release_errors(lineage, release, corpus, report, event, events=None):
    catalog = v.catalog_from_bundle(lineage)
    return v.validate_release_manifest(
        release, ctx=CTX, artifacts=catalog.artifacts,
        corpus_manifests={corpus["corpus_release_id"]: corpus},
        promotion_events=events if events is not None else {event["promotion_event_id"]: event},
        quality_reports={report["quality_report_id"]: report},
        run_outputs=catalog.run_outputs,
    )


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

bad_event = copy.deepcopy(event); bad_event["target_release_id"] = uid(962)
checks.append(("wrong promotion target", release_errors(lineage, release, rel_corpus, report, bad_event)))

restricted = copy.deepcopy(lineage)
restricted["artifacts"][-1]["access_license"]["access_class"] = "restricted-license"
checks.append(("restricted public artifact", release_errors(restricted, release, rel_corpus, report, event)))

mismatch = copy.deepcopy(lineage)
mismatch["artifacts"][-1]["corpus_release_id"] = uid(963)
checks.append(("corpus mismatch", release_errors(mismatch, release, rel_corpus, report, event)))

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
print(f"AUDIT PASS: {len(checks)} expected failures + exact lineage chain")
