import copy
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from pro_adherence import materialize as m
from pro_adherence import stage0_fixture as f
from pro_adherence import validate as v

_PREQA_SPEC = importlib.util.spec_from_file_location("preqa_closure", ROOT / "scripts/pre_qa_gate.py")
PREQA = importlib.util.module_from_spec(_PREQA_SPEC)
_PREQA_SPEC.loader.exec_module(PREQA)


def load_lineage():
    return v.load_json(ROOT / "contracts/manifests/minimal_lineage.example.json")


def uid(n):
    return f"018f0c50-7b1d-7cc3-8a5b-{n:012d}"


def add_run(bundle, run_id, input_ids, output_ids):
    run = copy.deepcopy(bundle["runs"][0])
    run["run_id"] = run_id
    bundle["runs"].append(run)
    for n, artifact_id in enumerate(input_ids):
        bundle["run_inputs"].append({
            "record_type": "run_input", "run_id": run_id,
            "artifact_id": artifact_id, "role": f"input_{n}",
        })
    for n, artifact_id in enumerate(output_ids):
        bundle["run_outputs"].append({
            "record_type": "run_output", "run_id": run_id,
            "artifact_id": artifact_id, "role": f"result_{n}",
        })


def add_artifact(bundle, artifact_id, *, source_fetch_id=None):
    artifact = copy.deepcopy(bundle["artifacts"][-1])
    artifact["artifact_id"] = artifact_id
    artifact["content_hash"] = f"{int(artifact_id[-2:], 16) % 16:x}" * 64
    artifact["uri"] = f"derived/synthetic/{artifact_id[-12:]}.json"
    artifact["source_fetch_id"] = source_fetch_id
    bundle["artifacts"].append(artifact)
    return artifact


def fixture_catalog(payload=None):
    fx = f.build_fixture(ROOT, payload=payload)
    errors = []
    catalog = v.catalog_from_bundle(fx["lineage"], errors)
    v.add_evidence_record(catalog, fx["report"], errors)
    v.add_evidence_record(catalog, fx["event"], errors)
    if errors:
        raise AssertionError(errors)
    corpora = {fx["corpus"]["corpus_release_id"]: fx["corpus"]}
    lineage_ids = {fx["lineage"]["root_output_artifact_id"]}
    return fx, catalog, corpora, lineage_ids


class LineageCycleSweepTests(unittest.TestCase):
    def test_self_loop_rejected(self):
        b = load_lineage()
        root = b["root_output_artifact_id"]
        b["run_inputs"][0]["artifact_id"] = root
        with self.assertRaisesRegex(v.ValidationFailure, "cycle"):
            v.reconstruct_lineage(b, root)

    def test_two_node_cycle_rejected(self):
        b = load_lineage()
        root = b["root_output_artifact_id"]
        canonical = b["run_inputs"][0]["artifact_id"]
        add_run(b, uid(1101), [root], [canonical])
        with self.assertRaisesRegex(v.ValidationFailure, "cycle"):
            v.reconstruct_lineage(b, root)

    def test_long_cycle_rejected(self):
        b = load_lineage()
        root = b["root_output_artifact_id"]
        canonical = b["run_inputs"][0]["artifact_id"]
        middle = uid(1102)
        add_artifact(b, middle)
        add_run(b, uid(1103), [root], [middle])
        add_run(b, uid(1104), [middle], [canonical])
        with self.assertRaisesRegex(v.ValidationFailure, "cycle"):
            v.reconstruct_lineage(b, root)

    def test_descendant_cycle_rejected(self):
        b = load_lineage()
        root = b["root_output_artifact_id"]
        canonical = b["run_inputs"][0]["artifact_id"]
        add_run(b, uid(1105), [root], [canonical])
        errors = v.validate_lineage(b)
        self.assertTrue(any("cycle" in e for e in errors), errors)

    def test_valid_chain_and_determinism(self):
        b = load_lineage()
        first = v.reconstruct_lineage(b, b["root_output_artifact_id"])
        second = v.reconstruct_lineage(b, b["root_output_artifact_id"])
        self.assertEqual(first, second)

    def test_branching_dag(self):
        b = load_lineage()
        root = b["root_output_artifact_id"]
        c1, c2 = uid(1110), uid(1111)
        add_artifact(b, c1)
        add_artifact(b, c2)
        add_run(b, uid(1112), [root], [c1])
        add_run(b, uid(1113), [root], [c2])
        result = v.reconstruct_lineage(b, root)
        self.assertEqual(result["descendant_artifact_ids"], sorted([c1, c2]))

    def test_disconnected_acyclic_component(self):
        b = load_lineage()
        a, z = uid(1120), uid(1121)
        add_artifact(b, a)
        add_artifact(b, z)
        add_run(b, uid(1122), [a], [z])
        self.assertEqual(v.validate_lineage(b), [])

    def test_duplicate_producer_still_rejected(self):
        b = load_lineage()
        root = b["root_output_artifact_id"]
        canonical = b["run_inputs"][0]["artifact_id"]
        add_run(b, uid(1130), [canonical], [root])
        errors = v.validate_lineage(b)
        self.assertTrue(any("duplicate producing runs" in e or "duplicate producer" in e for e in errors), errors)

    def test_converging_diamond_not_false_cycle(self):
        b = load_lineage()
        other = uid(1140)
        source_fetch_id = b["artifacts"][1]["source_fetch_id"]
        add_artifact(b, other, source_fetch_id=source_fetch_id)
        b["run_inputs"].append({
            "record_type": "run_input",
            "run_id": b["runs"][0]["run_id"],
            "artifact_id": other,
            "role": "second_input",
        })
        self.assertEqual(v.validate_lineage(b), [])


class BoundarySweepTests(unittest.TestCase):
    def test_all_forbidden_prefix_families_and_windows_paths(self):
        paths = [
            "data/raw/x", "data/normalized/x", "data/canonical/x", "data/derived/x",
            "data/research/x", "data/restricted/x", "research/x", "restricted/x",
            r"data\research\windows.json", r"data\restricted\windows.json",
        ]
        errors = v.validate_public_paths(paths)
        self.assertEqual(len(errors), len(paths), errors)

    def test_nested_secret_variants(self):
        paths = [
            "nested/.env", "nested/.env.prod", "nested/secrets/config.json",
            "nested/secrets.prod", "keys/private.key", "ssh/id_rsa", "ssh/id_ed25519",
        ]
        errors = v.validate_public_paths(paths)
        self.assertEqual(len(errors), len(paths), errors)
        self.assertEqual(v.validate_public_paths(["nested/.env.example"]), [])

    def test_serving_placeholder_rule_is_explicit(self):
        self.assertEqual(v.validate_public_paths(["serving/data/releases/.gitkeep"]), [])
        errors = v.validate_public_paths(["serving/data/releases/arbitrary.json"])
        self.assertTrue(any("release-selected" in e for e in errors), errors)

    def test_gitignore_covers_boundary_families(self):
        text = (ROOT / ".gitignore").read_text()
        for item in ("/data/research/", "/data/restricted/", "secrets/", "id_rsa", "id_ed25519"):
            self.assertIn(item, text)


class MaterializationSweepTests(unittest.TestCase):
    def _source(self, td, data=None):
        path = Path(td) / "source.json"
        if data is None:
            data = (ROOT / "tests/fixtures/stage0_materialization/public-artifact.json").read_bytes()
        path.write_bytes(data)
        return path

    def test_valid_selected_public_payload(self):
        fx, catalog, corpora, lineage_ids = fixture_catalog()
        with tempfile.TemporaryDirectory() as td:
            src = self._source(td)
            out = Path(td) / "out"
            result = m.materialize_release(
                fx["release"], catalog=catalog, corpora=corpora,
                lineage_artifact_ids=lineage_ids,
                artifact_sources={fx["artifact_id"]: src}, output_dir=out,
            )
            self.assertTrue((out / fx["spec"]["public_path"]).is_file())
            self.assertRegex(result["bundle_tree_hash"], r"^[0-9a-f]{64}$")

    def test_public_artifact_without_explicit_selection_fails(self):
        fx, catalog, corpora, lineage_ids = fixture_catalog()
        with tempfile.TemporaryDirectory() as td:
            src = self._source(td)
            errors = m.validate_materialization_inputs(
                fx["release"], catalog=catalog, corpora=corpora,
                lineage_artifact_ids=lineage_ids,
                artifact_sources={fx["artifact_id"]: src, uid(1200): src},
            )
            self.assertTrue(any("extra/unselected" in e for e in errors), errors)

    def test_selected_payload_hash_mismatch_fails(self):
        fx, catalog, corpora, lineage_ids = fixture_catalog()
        with tempfile.TemporaryDirectory() as td:
            src = self._source(td, b"tampered\n")
            errors = m.validate_materialization_inputs(
                fx["release"], catalog=catalog, corpora=corpora,
                lineage_artifact_ids=lineage_ids,
                artifact_sources={fx["artifact_id"]: src},
            )
            self.assertTrue(any("payload hash mismatch" in e for e in errors), errors)

    def test_restricted_and_project_internal_artifacts_fail(self):
        for access_class in ("restricted-license", "project-internal"):
            with self.subTest(access_class=access_class):
                fx, catalog, corpora, lineage_ids = fixture_catalog()
                artifact = catalog.artifacts[fx["artifact_id"]]
                artifact["access_license"]["access_class"] = access_class
                with tempfile.TemporaryDirectory() as td:
                    src = self._source(td)
                    errors = m.validate_materialization_inputs(
                        fx["release"], catalog=catalog, corpora=corpora,
                        lineage_artifact_ids=lineage_ids,
                        artifact_sources={fx["artifact_id"]: src},
                    )
                    self.assertTrue(errors)

    def test_selected_publication_permission_mismatch_fails(self):
        fx, catalog, corpora, lineage_ids = fixture_catalog()
        artifact = catalog.artifacts[fx["artifact_id"]]
        artifact["access_license"]["publication_permissions"]["derived"] = "deny"
        fx["release"]["artifacts"][0]["access_license"] = copy.deepcopy(artifact["access_license"])
        fx["release"]["manifest_hash"] = v.recompute_manifest_hash(fx["release"])
        with tempfile.TemporaryDirectory() as td:
            src = self._source(td)
            errors = m.validate_materialization_inputs(
                fx["release"], catalog=catalog, corpora=corpora,
                lineage_artifact_ids=lineage_ids,
                artifact_sources={fx["artifact_id"]: src},
            )
            self.assertTrue(any("not publishable" in e for e in errors), errors)

    def test_raw_or_research_uri_cannot_be_serving_source(self):
        fx, catalog, corpora, lineage_ids = fixture_catalog()
        catalog.artifacts[fx["artifact_id"]]["uri"] = "data/research/copied.json"
        with tempfile.TemporaryDirectory() as td:
            src = self._source(td)
            errors = m.validate_materialization_inputs(
                fx["release"], catalog=catalog, corpora=corpora,
                lineage_artifact_ids=lineage_ids,
                artifact_sources={fx["artifact_id"]: src},
            )
            self.assertTrue(any("forbidden raw/research source" in e for e in errors), errors)

    def test_changed_input_changes_bundle_hash_when_manifest_reconciled(self):
        with tempfile.TemporaryDirectory() as td:
            hashes = []
            for n, data in enumerate((b'{"stage0":"A"}\n', b'{"stage0":"B"}\n')):
                fx, catalog, corpora, lineage_ids = fixture_catalog(payload=data)
                src = Path(td) / f"source-{n}.json"
                src.write_bytes(data)
                out = Path(td) / f"out-{n}"
                result = m.materialize_release(
                    fx["release"], catalog=catalog, corpora=corpora,
                    lineage_artifact_ids=lineage_ids,
                    artifact_sources={fx["artifact_id"]: src}, output_dir=out,
                )
                hashes.append(result["bundle_tree_hash"])
            self.assertNotEqual(hashes[0], hashes[1])


class StatusClassSweepTests(unittest.TestCase):
    def test_stale_live_claim_new_markdown_fails(self):
        self.assertTrue(PREQA.scan_live_status("docs/new.md", "# x\nStage 0 = OPEN\n"))

    def test_stale_nested_handoff_fails_without_marker(self):
        self.assertTrue(PREQA.scan_live_status(
            "docs/handoffs/nested/x.md", "# x\nQA-S0-007 — OPEN / BLOCKING\n"
        ))

    def test_historical_record_allowed(self):
        self.assertEqual(PREQA.scan_live_status(
            "docs/handoffs/x.md",
            "> **HISTORICAL / SUPERSEDED** snapshot\nQA-S0-007 — OPEN / BLOCKING\n",
        ), [])

    def test_current_doc_reference_only_allowed(self):
        self.assertEqual(PREQA.scan_live_status(
            "docs/current.md",
            "# x\nOperational status is maintained only in project `07_STAGE_STATUS`.\n",
        ), [])


class RuntimeEnvelopeTests(unittest.TestCase):
    def test_oci_local_clone_ownership_guard_covers_worktree_and_gitdir(self):
        text = (ROOT / "scripts/run_pre_qa_exact_runtime.sh").read_text()
        self.assertIn("safe.directory /repo", text)
        self.assertIn("safe.directory /repo/.git", text)

    def test_exact_and_source_fallback_include_full_closure_sequence(self):
        for rel in (
            "scripts/run_pre_qa_exact_runtime.sh",
            "scripts/run_pre_qa_source_fallback.sh",
        ):
            text = (ROOT / rel).read_text()
            self.assertIn("scripts/stage0_e2e.py", text)
            self.assertIn("scripts/stage0_mutation_audit.py", text)
            self.assertIn("scripts/stage0_closure_mutation_audit.py", text)


class E2ESmokeTests(unittest.TestCase):
    def test_canonical_e2e(self):
        p = subprocess.run(
            [sys.executable, str(ROOT / "scripts/stage0_e2e.py")],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
