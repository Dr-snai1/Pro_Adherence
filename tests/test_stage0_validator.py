import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pro_adherence import validate as v
from pro_adherence import computation_signature as c


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def uid(n):
    return f"018f0c50-7b1d-7cc3-8a5b-{n:012d}"


def set_hash(manifest):
    manifest["manifest_hash"] = v.recompute_manifest_hash(manifest)
    return manifest


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


def promoted_fixture():
    lineage = load("contracts/manifests/minimal_lineage.example.json")
    artifact = lineage["artifacts"][-1]
    artifact["access_license"] = public_access()
    release_id = uid(900)
    report_id = uid(901)
    event_id = uid(902)
    release = {
        "manifest_version": "1.0.0",
        "release_id": release_id,
        "status": "promoted",
        "corpus_release_id": lineage["corpus_release_ids"][0],
        "artifacts": [{
            "artifact_id": artifact["artifact_id"],
            "artifact_type": artifact["artifact_type"],
            "content_hash": artifact["content_hash"],
            "schema_version": artifact["schema_version"],
            "role": "result",
            "public_path": "data/result.json",
            "publication_permission_basis": "derived",
            "access_license": copy.deepcopy(artifact["access_license"]),
        }],
        "promotion_event_ids": [event_id],
        "manifest_hash": "",
        "created_at": "2026-10-08T00:20:00Z",
        "superseded_by": None,
    }
    set_hash(release)
    report = {
        "record_type": "quality_report",
        "quality_report_id": report_id,
        "subject_artifact_id": artifact["artifact_id"],
        "status": "pass",
        "checks": [{"check_id": "fixture", "status": "pass", "message": None, "evidence_ref": None}],
        "created_at": "2026-10-08T00:19:00Z",
    }
    event = {
        "record_type": "promotion_event",
        "promotion_event_id": event_id,
        "artifact_ids": [artifact["artifact_id"]],
        "quality_report_ids": [report_id],
        "decision": "promoted",
        "target_release_id": release_id,
        "created_at": "2026-10-08T00:20:00Z",
    }
    corpus = load("contracts/manifests/empty_corpus.manifest.json")
    corpus["corpus_release_id"] = lineage["corpus_release_ids"][0]
    set_hash(corpus)
    return lineage, release, corpus, report, event


class Stage0ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = v.SchemaContext.from_repo(ROOT)

    def test_valid_minimal_lineage_passes(self):
        bundle = load("contracts/manifests/minimal_lineage.example.json")
        self.assertEqual(v.validate_lineage(bundle, self.ctx), [])

    def test_dangling_refs_fail(self):
        bundle = load("contracts/manifests/minimal_lineage.example.json")
        bundle["run_inputs"][0]["artifact_id"] = uid(999)
        self.assertTrue(any("missing artifact" in e for e in v.validate_lineage(bundle, self.ctx)))

    def test_missing_lineage_reference_classes_fail(self):
        base = load("contracts/manifests/minimal_lineage.example.json")
        cases = [
            ("run", lambda b: b["runs"].clear(), "missing run"),
            ("input artifact", lambda b: b["artifacts"].pop(1), "missing artifact"),
            ("code", lambda b: b["code_refs"].clear(), "missing code_ref_id"),
            ("config", lambda b: b["config_refs"].clear(), "missing config_ref_id"),
            ("environment", lambda b: b["environment_refs"].clear(), "missing environment_ref_id"),
            ("model", lambda b: b["model_refs"].clear(), "missing model_ref_id"),
        ]
        for name, mutate, expected in cases:
            with self.subTest(name=name):
                bundle = copy.deepcopy(base)
                mutate(bundle)
                self.assertTrue(any(expected in e for e in v.validate_lineage(bundle, self.ctx)))

    def test_root_lineage_requires_relevant_source_and_corpus(self):
        base = load("contracts/manifests/minimal_lineage.example.json")

        no_source = copy.deepcopy(base)
        no_source["artifacts"][1]["source_fetch_id"] = None
        self.assertTrue(any(
            "no relevant source fetch" in e for e in v.validate_lineage(no_source, self.ctx)
        ))

        no_corpus = copy.deepcopy(base)
        for artifact in no_corpus["artifacts"]:
            artifact["corpus_release_id"] = None
        for run in no_corpus["runs"]:
            run["corpus_release_id"] = None
        self.assertTrue(any(
            "no relevant corpus release" in e for e in v.validate_lineage(no_corpus, self.ctx)
        ))

    def test_duplicate_producing_run_fails(self):
        bundle = load("contracts/manifests/minimal_lineage.example.json")
        new_run = copy.deepcopy(bundle["runs"][0])
        new_run["run_id"] = uid(998)
        bundle["runs"].append(new_run)
        extra = copy.deepcopy(bundle["run_outputs"][0])
        extra["run_id"] = new_run["run_id"]
        bundle["run_outputs"].append(extra)
        self.assertTrue(any("duplicate producing runs" in e for e in v.validate_lineage(bundle, self.ctx)))

    def test_broken_source_lineage_fails(self):
        bundle = load("contracts/manifests/minimal_lineage.example.json")
        bundle["source_fetches"][0]["raw_artifact_id"] = uid(997)
        self.assertTrue(any("missing raw artifact" in e for e in v.validate_lineage(bundle, self.ctx)))

    def test_lineage_reconstruction_exact(self):
        bundle = load("contracts/manifests/minimal_lineage.example.json")
        result = v.reconstruct_lineage(bundle, bundle["root_output_artifact_id"])
        self.assertEqual(result["root_producing_run_id"], bundle["runs"][0]["run_id"])
        self.assertEqual(result["direct_input_artifact_ids"], [bundle["run_inputs"][0]["artifact_id"]])
        self.assertEqual(
            result["ancestor_artifact_ids"],
            sorted([bundle["run_inputs"][0]["artifact_id"], bundle["source_fetches"][0]["raw_artifact_id"]]),
        )
        self.assertEqual(result["source_fetch_ids"], [bundle["source_fetches"][0]["source_fetch_id"]])
        self.assertEqual(result["code_ref_ids"], [bundle["code_refs"][0]["code_ref_id"]])
        self.assertEqual(result["config_ref_ids"], [bundle["config_refs"][0]["config_ref_id"]])
        self.assertEqual(result["model_ref_ids"], [bundle["model_refs"][0]["model_ref_id"]])
        self.assertEqual(result["environment_ref_ids"], [bundle["environment_refs"][0]["environment_ref_id"]])

    def test_valid_empty_corpus_passes(self):
        corpus = load("contracts/manifests/empty_corpus.manifest.json")
        self.assertEqual(v.validate_corpus_manifest(corpus, root=ROOT, ctx=self.ctx, artifacts={}), [])

    def test_article_count_mismatch_fails(self):
        corpus = load("contracts/manifests/empty_corpus.manifest.json")
        corpus["article_count"] = 1
        set_hash(corpus)
        self.assertTrue(any("article_count" in e for e in v.validate_corpus_manifest(corpus, root=ROOT, ctx=self.ctx, artifacts={})))

    def test_corpus_input_artifact_reconciliation(self):
        corpus = load("contracts/manifests/empty_corpus.manifest.json")
        lineage = load("contracts/manifests/minimal_lineage.example.json")
        catalog = v.catalog_from_bundle(lineage).artifacts
        artifact = lineage["artifacts"][0]
        corpus["input_artifacts"] = [{
            "artifact_id": artifact["artifact_id"],
            "content_hash": artifact["content_hash"],
        }]
        set_hash(corpus)
        self.assertEqual(
            v.validate_corpus_manifest(corpus, root=ROOT, ctx=self.ctx, artifacts=catalog), []
        )

        bad_hash = copy.deepcopy(corpus)
        bad_hash["input_artifacts"][0]["content_hash"] = "0" * 64
        set_hash(bad_hash)
        self.assertTrue(any(
            "input artifact hash mismatch" in e
            for e in v.validate_corpus_manifest(bad_hash, root=ROOT, ctx=self.ctx, artifacts=catalog)
        ))

        dangling = copy.deepcopy(corpus)
        dangling["input_artifacts"][0]["artifact_id"] = uid(996)
        set_hash(dangling)
        self.assertTrue(any(
            "missing input artifact" in e
            for e in v.validate_corpus_manifest(dangling, root=ROOT, ctx=self.ctx, artifacts=catalog)
        ))

    def test_policy_hash_mismatch_fails(self):
        corpus = load("contracts/manifests/empty_corpus.manifest.json")
        corpus["inclusion_policy"]["content_hash"] = "0" * 64
        set_hash(corpus)
        self.assertTrue(any("inclusion_policy hash mismatch" in e for e in v.validate_corpus_manifest(corpus, root=ROOT, ctx=self.ctx, artifacts={})))

    def test_corpus_manifest_hash_mismatch_fails(self):
        corpus = load("contracts/manifests/empty_corpus.manifest.json")
        corpus["manifest_hash"] = "0" * 64
        self.assertTrue(any("manifest_hash mismatch" in e for e in v.validate_corpus_manifest(corpus, root=ROOT, ctx=self.ctx, artifacts={})))

    def test_valid_empty_draft_release_passes(self):
        release = load("contracts/manifests/empty_release.manifest.json")
        self.assertEqual(v.validate_release_manifest(release, ctx=self.ctx), [])

    def test_empty_promoted_release_fails(self):
        release = load("contracts/manifests/empty_release.manifest.json")
        release["status"] = "promoted"
        release["corpus_release_id"] = uid(910)
        set_hash(release)
        errors = v.validate_release_manifest(release, ctx=self.ctx, corpus_manifests={})
        self.assertTrue(errors)

    def test_valid_promoted_release_passes(self):
        lineage, release, corpus, report, event = promoted_fixture()
        catalog = v.catalog_from_bundle(lineage)
        errors = v.validate_release_manifest(
            release, ctx=self.ctx, artifacts=catalog.artifacts,
            corpus_manifests={corpus["corpus_release_id"]: corpus},
            promotion_events={event["promotion_event_id"]: event},
            quality_reports={report["quality_report_id"]: report},
            run_outputs=catalog.run_outputs,
            lineage_artifact_ids={release["artifacts"][0]["artifact_id"]},
        )
        self.assertEqual(errors, [])

    def test_promoted_release_without_validated_lineage_fails(self):
        lineage, release, corpus, report, event = promoted_fixture()
        catalog = v.catalog_from_bundle(lineage)
        errors = v.validate_release_manifest(
            release, ctx=self.ctx, artifacts=catalog.artifacts,
            corpus_manifests={corpus["corpus_release_id"]: corpus},
            promotion_events={event["promotion_event_id"]: event},
            quality_reports={report["quality_report_id"]: report},
            run_outputs=catalog.run_outputs,
            lineage_artifact_ids=set(),
        )
        self.assertTrue(any("lacks validated complete lineage" in e for e in errors))

    def test_missing_promotion_event_fails(self):
        lineage, release, corpus, report, event = promoted_fixture()
        catalog = v.catalog_from_bundle(lineage)
        errors = v.validate_release_manifest(
            release, ctx=self.ctx, artifacts=catalog.artifacts,
            corpus_manifests={corpus["corpus_release_id"]: corpus},
            promotion_events={}, quality_reports={report["quality_report_id"]: report},
            run_outputs=catalog.run_outputs,
            lineage_artifact_ids={release["artifacts"][0]["artifact_id"]},
        )
        self.assertTrue(any("missing promotion_event" in e for e in errors))

    def test_missing_quality_report_fails(self):
        lineage, release, corpus, report, event = promoted_fixture()
        catalog = v.catalog_from_bundle(lineage)
        errors = v.validate_release_manifest(
            release, ctx=self.ctx, artifacts=catalog.artifacts,
            corpus_manifests={corpus["corpus_release_id"]: corpus},
            promotion_events={event["promotion_event_id"]: event},
            quality_reports={},
            run_outputs=catalog.run_outputs,
            lineage_artifact_ids={release["artifacts"][0]["artifact_id"]},
        )
        self.assertTrue(any("missing quality_report" in e for e in errors))

    def test_wrong_target_release_fails(self):
        lineage, release, corpus, report, event = promoted_fixture()
        event["target_release_id"] = uid(911)
        catalog = v.catalog_from_bundle(lineage)
        errors = v.validate_release_manifest(
            release, ctx=self.ctx, artifacts=catalog.artifacts,
            corpus_manifests={corpus["corpus_release_id"]: corpus},
            promotion_events={event["promotion_event_id"]: event},
            quality_reports={report["quality_report_id"]: report},
            run_outputs=catalog.run_outputs,
            lineage_artifact_ids={release["artifacts"][0]["artifact_id"]},
        )
        self.assertTrue(any("wrong target_release_id" in e for e in errors))

    def test_release_artifact_without_promotion_coverage_fails(self):
        lineage, release, corpus, report, event = promoted_fixture()
        event["artifact_ids"] = [uid(912)]
        catalog = v.catalog_from_bundle(lineage)
        errors = v.validate_release_manifest(
            release, ctx=self.ctx, artifacts=catalog.artifacts,
            corpus_manifests={corpus["corpus_release_id"]: corpus},
            promotion_events={event["promotion_event_id"]: event},
            quality_reports={report["quality_report_id"]: report},
            run_outputs=catalog.run_outputs,
            lineage_artifact_ids={release["artifacts"][0]["artifact_id"]},
        )
        self.assertTrue(any("lacks promotion coverage" in e for e in errors))

    def test_restricted_artifact_in_public_release_fails(self):
        lineage, release, corpus, report, event = promoted_fixture()
        lineage["artifacts"][-1]["access_license"]["access_class"] = "restricted-license"
        catalog = v.catalog_from_bundle(lineage)
        errors = v.validate_release_manifest(
            release, ctx=self.ctx, artifacts=catalog.artifacts,
            corpus_manifests={corpus["corpus_release_id"]: corpus},
            promotion_events={event["promotion_event_id"]: event},
            quality_reports={report["quality_report_id"]: report},
            run_outputs=catalog.run_outputs,
            lineage_artifact_ids={release["artifacts"][0]["artifact_id"]},
        )
        self.assertTrue(any("not publishable" in e for e in errors))

    def test_artifact_hash_mismatch_fails(self):
        lineage, release, corpus, report, event = promoted_fixture()
        release["artifacts"][0]["content_hash"] = "1" * 64
        set_hash(release)
        catalog = v.catalog_from_bundle(lineage)
        errors = v.validate_release_manifest(
            release, ctx=self.ctx, artifacts=catalog.artifacts,
            corpus_manifests={corpus["corpus_release_id"]: corpus},
            promotion_events={event["promotion_event_id"]: event},
            quality_reports={report["quality_report_id"]: report},
            run_outputs=catalog.run_outputs,
            lineage_artifact_ids={release["artifacts"][0]["artifact_id"]},
        )
        self.assertTrue(any("content_hash mismatch" in e for e in errors))

    def test_corpus_mismatch_fails(self):
        lineage, release, corpus, report, event = promoted_fixture()
        lineage["artifacts"][-1]["corpus_release_id"] = uid(913)
        catalog = v.catalog_from_bundle(lineage)
        errors = v.validate_release_manifest(
            release, ctx=self.ctx, artifacts=catalog.artifacts,
            corpus_manifests={corpus["corpus_release_id"]: corpus},
            promotion_events={event["promotion_event_id"]: event},
            quality_reports={report["quality_report_id"]: report},
            run_outputs=catalog.run_outputs,
            lineage_artifact_ids={release["artifacts"][0]["artifact_id"]},
        )
        self.assertTrue(any("corpus mismatch" in e for e in errors))

    def test_mutable_model_revision_alias_direct_helper_fails(self):
        model = load("contracts/manifests/minimal_lineage.example.json")["model_refs"][0]
        for alias in ("latest", "current", "HEAD", "head", "main", "master", "tip", "trunk", "default", "stable", "newest"):
            with self.subTest(alias=alias):
                mutated = dict(model, immutable_revision=alias)
                with self.assertRaises(c.SignatureError):
                    c.model_descriptor(mutated)

    def test_repository_boundary_clean(self):
        self.assertEqual(v.validate_repository_boundary(ROOT), [])

    def test_forbidden_tracked_research_path_fails(self):
        errors = v.validate_public_paths(["docs/mentions-research.md", "research/output.json"])
        self.assertEqual(len(errors), 1)
        self.assertIn("research/output.json", errors[0])


    def test_forbidden_secret_path_fails(self):
        errors = v.validate_public_paths([".env", "./.env.local", ".env.example"])
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(".env" in e for e in errors))

if __name__ == "__main__":
    unittest.main()
