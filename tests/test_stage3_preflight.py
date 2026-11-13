"""No-network, no-model-load synthetic gates for the Stage3 upstream preflight."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pro_adherence import stage3_preflight as pre


CONFIG = Path(__file__).resolve().parents[1] / "configs" / "stage3" / "model_preflight_pins.json"


class Stage3ModelPreflightTests(unittest.TestCase):
    def setUp(self):
        self.config = pre.load_config(CONFIG)

    def test_official_full_revision_pins_and_no_publication(self):
        self.assertEqual(set(self.config["upstream_revisions"]), set(pre.EXACT_UPSTREAM))
        for key, (repo, revision) in pre.EXACT_UPSTREAM.items():
            self.assertEqual(self.config["upstream_revisions"][key]["repository"], repo)
            self.assertEqual(self.config["upstream_revisions"][key]["revision"], revision)
            self.assertEqual(len(revision), 40)
        self.assertEqual(self.config["owner_approved_analytical_population"]["eligible_count"], 57204)
        self.assertFalse(self.config["publication_authorized"])

    def test_refuse_mutated_science_upstream_or_private_scope(self):
        changes = [
            ("upstream_revisions", "pubmedbert", "revision", "main"),
            ("upstream_revisions", "specter2_base", "repository", "allenai/specter2"),
            ("upstream_revisions", "specter2_proximity", "revision", "a" * 40),
        ]
        for _, component, field, altered in changes:
            with self.subTest(component=component, field=field):
                cfg = deepcopy(self.config)
                cfg["upstream_revisions"][component][field] = altered
                with self.assertRaises(pre.Stage3PreflightError):
                    pre.verify_static_preflight_config(cfg)
        mutated = deepcopy(self.config)
        mutated["publication_authorized"] = True
        with self.assertRaisesRegex(pre.Stage3PreflightError, "cannot be published"):
            pre.verify_static_preflight_config(mutated)
        mutated = deepcopy(self.config)
        mutated["owner_approved_analytical_population"]["eligible_count"] = 57207
        with self.assertRaisesRegex(pre.Stage3PreflightError, "cohort identity"):
            pre.verify_static_preflight_config(mutated)

    def test_fail_closed_when_model_bytes_runtime_graph_or_authorization_absent(self):
        report = pre.audit_stage3_preflight(self.config)
        self.assertTrue(report["preflight_only"])
        self.assertFalse(report["owner_compute_authorized"])
        self.assertFalse(report["publication_authorized"])
        self.assertFalse(report["upstream_commit_refs_verified"])
        self.assertTrue(report["upstream_commit_refs_match_approved_config"])
        for lens, r in report["lenses"].items():
            with self.subTest(lens=lens):
                self.assertFalse(r["ready_for_owner_authorized_compute"])
                self.assertIn("PRIVATE_COHORT_FILE_NOT_SUPPLIED", r["blockers"])
                self.assertIn("OWNER_COMPUTE_GATE_NOT_GRANTED", r["blockers"])
                self.assertIn("EXACT_COMPATIBLE_RUNTIME_NOT_VERIFIED", r["blockers"])
        self.assertIn("CITATION_GRAPH_SNAPSHOT_NOT_VERIFIED", report["lenses"]["node2vec"]["blockers"])

    def test_offline_cli_emits_blockers_and_require_ready_exit_two(self):
        import os
        import subprocess
        import sys
        root = CONFIG.parents[2]
        env = dict(os.environ, PYTHONPATH=str(root / "src"))
        cmd = [
            sys.executable, "-m", "pro_adherence.stage3_preflight",
            "--config", str(CONFIG),
        ]
        result = subprocess.run(cmd, cwd=root, env=env,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["owner_compute_authorized"])
        self.assertTrue(all(
            not item["ready_for_owner_authorized_compute"]
            for item in report["lenses"].values()))
        strict = subprocess.run(cmd + ["--require-ready"], cwd=root, env=env,
                                capture_output=True, text=True, check=False)
        self.assertEqual(strict.returncode, 2, strict.stderr)

    def test_synthetic_ready_only_after_real_byte_hash_and_runtime_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            cohort_bytes = b"not-a-real-private-cohort\n"
            cohort = folder / "cohort.gz"
            cohort.write_bytes(cohort_bytes)
            cohort_sha = sha256(cohort_bytes).hexdigest()
            cfg = deepcopy(self.config)
            cfg["owner_approved_analytical_population"]["private_manifest_sha256"] = cohort_sha
            directories = {}
            trusted = {}
            for component, spec in cfg["upstream_revisions"].items():
                root = folder / component
                root.mkdir()
                directories[component] = root
                trusted[component] = {}
                for filename in spec["required_files"]:
                    content = (component + ":" + filename).encode("ascii")
                    (root / filename).write_bytes(content)
                    trusted[component][filename] = sha256(content).hexdigest()
            runtime = {
                "python": "3.13.16",
                "torch": "2.5.1",
                "transformers": "4.45.0",
                "tokenizers": "0.20.0",
                "adapters": "1.2.0",
                "node2vec_backend": "0.5.0",
                "lockfile_sha256": "f" * 64,
            }
            graph = {
                "source_directed_graph_sha256": "1" * 64,
                "training_undirected_graph_sha256": "2" * 64,
                "sorted_node_mapping_sha256": "3" * 64,
                "eligible_node_count": 57204,
                "training_orientation": "undirected",
                "source_orientation": "directed",
                "weights": "binary_unit",
            }
            with mock.patch.object(pre, "PRIVATE_COHORT_SHA", cohort_sha):
                # Even fully checksummed files cannot override the Stage gate.
                r = pre.audit_stage3_preflight(
                    cfg, private_cohort_path=cohort,
                    model_cache_dirs=directories,
                    authoritative_file_hashes=trusted,
                    exact_runtime_lock=runtime, graph_snapshot=graph,
                )
                for item in r["lenses"].values():
                    self.assertFalse(item["ready_for_owner_authorized_compute"])
                    self.assertIn("OWNER_COMPUTE_GATE_NOT_GRANTED", item["blockers"])
                    self.assertIn("RUNTIME_LOCK_BYTES_NOT_VERIFIED", item["blockers"])
                # Pure software readiness, not launching inference.
                r = pre.audit_stage3_preflight(
                    cfg, private_cohort_path=cohort,
                    model_cache_dirs=directories,
                    authoritative_file_hashes=trusted,
                    exact_runtime_lock=runtime, graph_snapshot=graph,
                    compute_authorized=True,
                )
                self.assertFalse(all(v["ready_for_owner_authorized_compute"] for v in r["lenses"].values()))
                self.assertIn("RUNTIME_LOCK_BYTES_NOT_VERIFIED", r["lenses"]["node2vec"]["blockers"])
                corrupted = folder / "pubmedbert" / "pytorch_model.bin"
                corrupted.write_bytes(b"different untrusted bytes")
                with self.assertRaisesRegex(pre.Stage3PreflightError, "model file checksum mismatch"):
                    pre.audit_stage3_preflight(
                        cfg, private_cohort_path=cohort,
                        model_cache_dirs=directories,
                        authoritative_file_hashes=trusted,
                        exact_runtime_lock=runtime, graph_snapshot=graph,
                    )
                bad_graph = {**graph, "eligible_node_count": 57207}
                with self.assertRaisesRegex(pre.Stage3PreflightError, "graph policy mismatch"):
                    pre.audit_stage3_preflight(cfg, graph_snapshot=bad_graph)

    def test_claimed_runtime_and_graph_sha_without_file_bytes_never_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            runtime_bytes = b"synthetic lock not installed\n"
            lock = folder / "runtime.lock"
            lock.write_bytes(runtime_bytes)
            digest = sha256(runtime_bytes).hexdigest()
            graph_data = {}
            graph_paths = {}
            for key in ("source_directed_graph_sha256", "training_undirected_graph_sha256",
                        "sorted_node_mapping_sha256"):
                p = folder / key
                p.write_bytes(key.encode("utf-8"))
                graph_data[key] = sha256(p.read_bytes()).hexdigest()
                graph_paths[key] = p
            graph = {**graph_data, "eligible_node_count": 57204,
                     "training_orientation": "undirected",
                     "source_orientation": "directed", "weights": "binary_unit"}
            runtime = {"python": "3.13.5", "torch": "2.5.1",
                       "transformers": "5.3.0", "tokenizers": "0.22.0",
                       "adapters": "1.3.0", "node2vec_backend": "0.5.0",
                       "lockfile_sha256": digest}
            report = pre.audit_stage3_preflight(
                self.config, exact_runtime_lock=runtime, graph_snapshot=graph,
                compute_authorized=True)
            self.assertIn("RUNTIME_LOCK_BYTES_NOT_VERIFIED",
                          report["lenses"]["node2vec"]["blockers"])
            self.assertIn("GRAPH_ARTIFACT_BYTES_NOT_VERIFIED:sorted_node_mapping_sha256",
                          report["lenses"]["node2vec"]["blockers"])
            self.assertIn("ADAPTERS_1_3_0_TRANSFORMERS_CONSTRAINT_CONFLICT",
                          report["lenses"]["specter2"]["blockers"])
            verified = pre.audit_stage3_preflight(
                self.config, exact_runtime_lock=runtime,
                exact_runtime_lock_path=lock, graph_snapshot=graph,
                graph_artifact_paths=graph_paths, compute_authorized=True)
            self.assertNotIn("RUNTIME_LOCK_BYTES_NOT_VERIFIED",
                             verified["lenses"]["node2vec"]["blockers"])
            self.assertFalse(verified["lenses"]["specter2"]["ready_for_owner_authorized_compute"])
            graph_paths["sorted_node_mapping_sha256"].write_bytes(b"mutated")
            with self.assertRaisesRegex(pre.Stage3PreflightError, "graph artifact SHA256 mismatch"):
                pre.audit_stage3_preflight(
                    self.config, exact_runtime_lock=runtime,
                    exact_runtime_lock_path=lock, graph_snapshot=graph,
                    graph_artifact_paths=graph_paths)


if __name__ == "__main__":
    unittest.main()
