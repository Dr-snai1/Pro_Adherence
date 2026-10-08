import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pro_adherence import validate as v

IDS = json.loads(
    (ROOT / "tests/fixtures/promotion_quality_cases.json").read_text(encoding="utf-8")
)


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def public_access():
    return {
        "access_class": "public",
        "license_class": "fixture",
        "license_status": "confirmed",
        "license_evidence_ref": "fixture",
        "publication_permissions": {
            "metadata": "allow",
            "raw_text": "deny",
            "derived": "allow",
        },
    }


def make_world():
    lineage = load("contracts/manifests/minimal_lineage.example.json")
    artifact_a = lineage["artifacts"][-1]
    artifact_a["access_license"] = public_access()
    root_run = lineage["runs"][0]["run_id"]

    artifact_b = copy.deepcopy(artifact_a)
    artifact_b["artifact_id"] = IDS["artifact_b"]
    artifact_b["uri"] = "derived/synthetic/direct-b.json"
    artifact_b["content_hash"] = "9" * 64
    artifact_b["created_at"] = "2026-10-08T00:00:04Z"
    lineage["artifacts"].append(artifact_b)
    lineage["run_outputs"].append({
        "record_type": "run_output",
        "run_id": root_run,
        "artifact_id": artifact_b["artifact_id"],
        "role": "result_b",
    })

    artifact_c = copy.deepcopy(artifact_a)
    artifact_c["artifact_id"] = IDS["artifact_c"]
    artifact_c["uri"] = "derived/synthetic/descendant-c.json"
    artifact_c["content_hash"] = "8" * 64
    artifact_c["created_at"] = "2026-10-08T00:00:06Z"
    lineage["artifacts"].append(artifact_c)

    descendant_run = copy.deepcopy(lineage["runs"][0])
    descendant_run["run_id"] = IDS["run_descendant"]
    descendant_run["run_type"] = "synthetic_descendant_compute"
    descendant_run["started_at"] = "2026-10-08T00:00:05Z"
    descendant_run["finished_at"] = "2026-10-08T00:00:06Z"
    lineage["runs"].append(descendant_run)
    lineage["run_inputs"].append({
        "record_type": "run_input",
        "run_id": descendant_run["run_id"],
        "artifact_id": artifact_a["artifact_id"],
        "role": "input",
    })
    lineage["run_outputs"].append({
        "record_type": "run_output",
        "run_id": descendant_run["run_id"],
        "artifact_id": artifact_c["artifact_id"],
        "role": "result",
    })

    corpus = load("contracts/manifests/empty_corpus.manifest.json")
    corpus["corpus_release_id"] = lineage["corpus_release_ids"][0]
    corpus["manifest_hash"] = v.recompute_manifest_hash(corpus)

    return {
        "lineage": lineage,
        "artifact_a": artifact_a,
        "artifact_b": artifact_b,
        "artifact_c": artifact_c,
        "root_run": root_run,
        "descendant_run": descendant_run["run_id"],
        "corpus": corpus,
    }


def report(name, *, artifact_id=None, run_id=None, status="pass", checks=("pass",)):
    value = {
        "record_type": "quality_report",
        "quality_report_id": IDS["reports"][name],
        "status": status,
        "checks": [
            {
                "check_id": f"check_{i}",
                "status": check_status,
                "message": None,
                "evidence_ref": None,
            }
            for i, check_status in enumerate(checks, 1)
        ],
        "created_at": "2026-10-08T00:10:00Z",
    }
    if artifact_id is not None:
        value["subject_artifact_id"] = artifact_id
    if run_id is not None:
        value["subject_run_id"] = run_id
    return value


def event(name, artifact_ids, report_ids, *, decision="promoted", target_release_id=None):
    value = {
        "record_type": "promotion_event",
        "promotion_event_id": IDS["events"][name],
        "artifact_ids": list(artifact_ids),
        "quality_report_ids": list(report_ids),
        "decision": decision,
        "created_at": "2026-10-08T00:11:00Z",
    }
    if target_release_id is not None:
        value["target_release_id"] = target_release_id
    return value


def release_item(artifact, index):
    return {
        "artifact_id": artifact["artifact_id"],
        "artifact_type": artifact["artifact_type"],
        "content_hash": artifact["content_hash"],
        "schema_version": artifact["schema_version"],
        "role": f"result_{index}",
        "public_path": f"data/result-{index}.json",
        "publication_permission_basis": "derived",
        "access_license": copy.deepcopy(artifact["access_license"]),
    }


def make_release(world, artifacts, event_ids):
    release = {
        "manifest_version": "1.0.0",
        "release_id": IDS["release"],
        "status": "promoted",
        "corpus_release_id": world["lineage"]["corpus_release_ids"][0],
        "artifacts": [release_item(artifact, i) for i, artifact in enumerate(artifacts, 1)],
        "promotion_event_ids": list(event_ids),
        "manifest_hash": "",
        "created_at": "2026-10-08T00:12:00Z",
        "superseded_by": None,
    }
    release["manifest_hash"] = v.recompute_manifest_hash(release)
    return release


def validate_release(world, release, events, reports):
    catalog = v.catalog_from_bundle(world["lineage"])
    return v.validate_release_manifest(
        release,
        ctx=v.SchemaContext.from_repo(ROOT),
        artifacts=catalog.artifacts,
        corpus_manifests={world["corpus"]["corpus_release_id"]: world["corpus"]},
        promotion_events={item["promotion_event_id"]: item for item in events},
        quality_reports={item["quality_report_id"]: item for item in reports},
        run_outputs=catalog.run_outputs,
        lineage_artifact_ids={item["artifact_id"] for item in release["artifacts"]},
    )


class PromotionQualityTests(unittest.TestCase):
    def test_artifact_scoped_pass_same_artifact_valid(self):
        w = make_world()
        r = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        e = event("primary", [w["artifact_a"]["artifact_id"]], [r["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertEqual(validate_release(w, rel, [e], [r]), [])

    def test_run_scoped_pass_direct_output_valid(self):
        w = make_world()
        r = report("run_pass", run_id=w["root_run"])
        e = event("primary", [w["artifact_a"]["artifact_id"]], [r["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertEqual(validate_release(w, rel, [e], [r]), [])

    def test_one_run_pass_covers_multiple_direct_outputs(self):
        w = make_world()
        r = report("run_pass", run_id=w["root_run"])
        ids = [w["artifact_a"]["artifact_id"], w["artifact_b"]["artifact_id"]]
        e = event("primary", ids, [r["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"], w["artifact_b"]], [e["promotion_event_id"]])
        self.assertEqual(validate_release(w, rel, [e], [r]), [])

    def test_pass_plus_pass_full_coverage_valid(self):
        w = make_world()
        a = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        b = report("artifact_pass_b", artifact_id=w["artifact_b"]["artifact_id"])
        ids = [w["artifact_a"]["artifact_id"], w["artifact_b"]["artifact_id"]]
        e = event("primary", ids, [a["quality_report_id"], b["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"], w["artifact_b"]], [e["promotion_event_id"]])
        self.assertEqual(validate_release(w, rel, [e], [a, b]), [])

    def test_historical_fail_not_in_evidence_set_does_not_block(self):
        w = make_world()
        p = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        f = report("fail", artifact_id=w["artifact_a"]["artifact_id"], status="fail", checks=("fail",))
        e = event("primary", [w["artifact_a"]["artifact_id"]], [p["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertEqual(validate_release(w, rel, [e], [p, f]), [])

    def test_rejected_warn_fail_is_valid_provenance_but_never_qualifies(self):
        w = make_world()
        warn = report("warn", artifact_id=w["artifact_a"]["artifact_id"], status="warn", checks=("warn",))
        fail = report("fail", artifact_id=w["artifact_a"]["artifact_id"], status="fail", checks=("fail",))
        e = event("primary", [w["artifact_a"]["artifact_id"]], [warn["quality_report_id"], fail["quality_report_id"]], decision="rejected")
        errors, qualifies = v.validate_promotion_event_quality(
            e,
            quality_reports={warn["quality_report_id"]: warn, fail["quality_report_id"]: fail},
            run_outputs=w["lineage"]["run_outputs"],
        )
        self.assertEqual(errors, [])
        self.assertFalse(qualifies)

    def test_warn_evidence_invalid_promotion(self):
        w = make_world()
        r = report("warn", artifact_id=w["artifact_a"]["artifact_id"], status="warn", checks=("warn",))
        e = event("primary", [w["artifact_a"]["artifact_id"]], [r["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertTrue(any("not qualifying PASS" in x for x in validate_release(w, rel, [e], [r])))

    def test_fail_evidence_invalid_promotion(self):
        w = make_world()
        r = report("fail", artifact_id=w["artifact_a"]["artifact_id"], status="fail", checks=("fail",))
        e = event("primary", [w["artifact_a"]["artifact_id"]], [r["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertTrue(any("not qualifying PASS" in x for x in validate_release(w, rel, [e], [r])))

    def test_pass_plus_warn_invalid(self):
        w = make_world()
        p = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        warn = report("warn", artifact_id=w["artifact_a"]["artifact_id"], status="warn", checks=("warn",))
        e = event("primary", [w["artifact_a"]["artifact_id"]], [p["quality_report_id"], warn["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertTrue(validate_release(w, rel, [e], [p, warn]))

    def test_pass_plus_fail_invalid(self):
        w = make_world()
        p = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        fail = report("fail", artifact_id=w["artifact_a"]["artifact_id"], status="fail", checks=("fail",))
        e = event("primary", [w["artifact_a"]["artifact_id"]], [p["quality_report_id"], fail["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertTrue(validate_release(w, rel, [e], [p, fail]))

    def test_declared_pass_with_warn_check_invalid(self):
        w = make_world()
        r = report("inconsistent", artifact_id=w["artifact_a"]["artifact_id"], status="pass", checks=("warn",))
        self.assertTrue(any("does not match effective status" in x for x in v.validate_quality_report(r)))

    def test_declared_pass_with_fail_check_invalid(self):
        w = make_world()
        r = report("inconsistent", artifact_id=w["artifact_a"]["artifact_id"], status="pass", checks=("fail",))
        self.assertTrue(any("does not match effective status" in x for x in v.validate_quality_report(r)))

    def test_declared_warn_with_all_pass_checks_invalid(self):
        w = make_world()
        r = report("inconsistent", artifact_id=w["artifact_a"]["artifact_id"], status="warn", checks=("pass", "pass"))
        self.assertTrue(any("does not match effective status" in x for x in v.validate_quality_report(r)))

    def test_declared_fail_without_fail_check_invalid(self):
        w = make_world()
        r = report("inconsistent", artifact_id=w["artifact_a"]["artifact_id"], status="fail", checks=("pass", "warn"))
        self.assertTrue(any("does not match effective status" in x for x in v.validate_quality_report(r)))

    def test_rejected_unrelated_report_is_invalid_provenance(self):
        w = make_world()
        r = report("unrelated", artifact_id=w["artifact_b"]["artifact_id"], status="warn", checks=("warn",))
        e = event("primary", [w["artifact_a"]["artifact_id"]], [r["quality_report_id"]], decision="rejected")
        errors, qualifies = v.validate_promotion_event_quality(
            e,
            quality_reports={r["quality_report_id"]: r},
            run_outputs=w["lineage"]["run_outputs"],
        )
        self.assertTrue(any("no applicable artifacts" in x for x in errors))
        self.assertFalse(qualifies)

    def test_two_valid_events_union_fully_covers_release(self):
        w = make_world()
        a = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        b = report("artifact_pass_b", artifact_id=w["artifact_b"]["artifact_id"])
        e1 = event("primary", [w["artifact_a"]["artifact_id"]], [a["quality_report_id"]], target_release_id=IDS["release"])
        e2 = event("secondary", [w["artifact_b"]["artifact_id"]], [b["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"], w["artifact_b"]], [e1["promotion_event_id"], e2["promotion_event_id"]])
        self.assertEqual(validate_release(w, rel, [e1, e2], [a, b]), [])

    def test_unrelated_artifact_scoped_pass_invalid(self):
        w = make_world()
        r = report("unrelated", artifact_id=w["artifact_b"]["artifact_id"])
        e = event("primary", [w["artifact_a"]["artifact_id"]], [r["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertTrue(any("no applicable artifacts" in x for x in validate_release(w, rel, [e], [r])))

    def test_run_scoped_pass_without_direct_output_invalid(self):
        w = make_world()
        r = report("run_pass", run_id=w["descendant_run"])
        e = event("primary", [w["artifact_a"]["artifact_id"]], [r["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertTrue(any("no applicable artifacts" in x for x in validate_release(w, rel, [e], [r])))

    def test_transitive_descendant_not_covered_by_ancestor_run(self):
        w = make_world()
        r = report("run_pass", run_id=w["root_run"])
        e = event("primary", [w["artifact_c"]["artifact_id"]], [r["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_c"]], [e["promotion_event_id"]])
        self.assertTrue(any("no applicable artifacts" in x for x in validate_release(w, rel, [e], [r])))

    def test_promoted_artifact_without_quality_coverage_invalid(self):
        w = make_world()
        r = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        ids = [w["artifact_a"]["artifact_id"], w["artifact_b"]["artifact_id"]]
        e = event("primary", ids, [r["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"], w["artifact_b"]], [e["promotion_event_id"]])
        self.assertTrue(any("lacks qualifying PASS quality coverage" in x for x in validate_release(w, rel, [e], [r])))

    def test_extra_unrelated_pass_in_exact_evidence_set_invalid(self):
        w = make_world()
        p = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        extra = report("unrelated", artifact_id=w["artifact_b"]["artifact_id"])
        e = event("primary", [w["artifact_a"]["artifact_id"]], [p["quality_report_id"], extra["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertTrue(any("no applicable artifacts" in x for x in validate_release(w, rel, [e], [p, extra])))

    def test_compute_asset_quality_report_is_not_implicit_coverage(self):
        w = make_world()
        implicit = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        referenced = report("unrelated", artifact_id=w["artifact_b"]["artifact_id"])
        compute_asset = {"quality_report_id": implicit["quality_report_id"]}
        self.assertNotEqual(compute_asset["quality_report_id"], referenced["quality_report_id"])
        e = event("primary", [w["artifact_a"]["artifact_id"]], [referenced["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        errors = validate_release(w, rel, [e], [implicit, referenced])
        self.assertTrue(any("lacks qualifying PASS quality coverage" in x for x in errors))

    def test_rejected_event_referenced_by_promoted_release_invalid(self):
        w = make_world()
        r = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        e = event("primary", [w["artifact_a"]["artifact_id"]], [r["quality_report_id"]], decision="rejected", target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertTrue(any("decision is not promoted" in x for x in validate_release(w, rel, [e], [r])))

    def test_event_target_release_mismatch_invalid(self):
        w = make_world()
        r = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        e = event("primary", [w["artifact_a"]["artifact_id"]], [r["quality_report_id"]], target_release_id=IDS["other_release"])
        rel = make_release(w, [w["artifact_a"]], [e["promotion_event_id"]])
        self.assertTrue(any("wrong target_release_id" in x for x in validate_release(w, rel, [e], [r])))

    def test_union_of_valid_events_must_cover_all_release_artifacts(self):
        w = make_world()
        a = report("artifact_pass", artifact_id=w["artifact_a"]["artifact_id"])
        e = event("primary", [w["artifact_a"]["artifact_id"]], [a["quality_report_id"]], target_release_id=IDS["release"])
        rel = make_release(w, [w["artifact_a"], w["artifact_b"]], [e["promotion_event_id"]])
        self.assertTrue(any(
            w["artifact_b"]["artifact_id"] in x and "lacks promotion coverage" in x
            for x in validate_release(w, rel, [e], [a])
        ))


if __name__ == "__main__":
    unittest.main()
