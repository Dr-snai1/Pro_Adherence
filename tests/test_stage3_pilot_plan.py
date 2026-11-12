"""No-compute deterministic arithmetic tests for Stage3 pilot plan."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from pro_adherence.stage3_pilot_plan import capacity_plan


class Stage3PilotTests(unittest.TestCase):
    def test_graph_facts_and_storage_math(self):
        r = capacity_plan()
        g = r["graph"]
        self.assertEqual(g["trainable_nonisolated_nodes"], 43608)
        self.assertEqual(g["walks_nonisolate"], 436080)
        self.assertEqual(g["nominal_nonisolate_walk_tokens"], 17443200)
        self.assertEqual(g["minimum_uint32_walk_token_bytes"], 69772800)
        self.assertEqual(g["node2vec_fixed_parameters"]["seed"], 20261031)
        self.assertEqual(g["training_unique_edges"], 328298)
        self.assertEqual(g["node2vec_fixed_parameters"]["negative"],5)
        self.assertEqual(g["node2vec_fixed_parameters"]["sample"],0.001)
        self.assertEqual(g["node2vec_fixed_parameters"]["hs"],0)
        self.assertTrue(r["node2vec_full_training_readiness"]["owner_full_training_authorized"])
        self.assertTrue(r["node2vec_full_training_readiness"]["production_vectors_generated"])
        self.assertTrue(r["node2vec_full_training_readiness"]["full_scale_duration_verified"])
        self.assertEqual(r["node2vec_verified_full_cpu_result"]["trained_vectors_128d"],43608)
        self.assertFalse(r["node2vec_verified_full_cpu_result"]["additional_compute_authorized"])
        self.assertFalse(r["node2vec_full_training_readiness"]["exact_dependency_wheel_hash_lock_verified"])
        self.assertEqual(r["storage_uncompressed_float32_lower_bound_bytes"]
                         ["combined_raw_and_unit"], 1099038720)
        self.assertFalse(r["owner_compute_authorized"])

    def test_no_invented_rates_cost_or_time(self):
        r = capacity_plan()
        for x in r["runtime_projections"].values():
            self.assertIsNone(x["hours"])
            self.assertIsNone(x["cost"])
        p = capacity_plan(pubmedbert_articles_per_s=2.0,
                          node2vec_tokens_per_s=10000.0,
                          pubmedbert_price_per_hour=1.25, node2vec_price_per_hour=0.0)
        self.assertAlmostEqual(p["runtime_projections"]
                               ["pubmedbert_single_encoder_two_poolings"]["hours"],
                               57204 / 2 / 3600)
        self.assertIsNone(p["runtime_projections"]["specter2_proximity"]["hours"])
        self.assertAlmostEqual(p["runtime_projections"]
                               ["node2vec_walk_generation_only"]["cost"],
                               0.0)

    def test_negative_invalid_input_rejected(self):
        for val in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(val=val):
                with self.assertRaises(ValueError):
                    capacity_plan(node2vec_tokens_per_s=val)

    def test_zero_cost_supported_and_invalid_prices_rejected(self):
        p = capacity_plan(node2vec_tokens_per_s=1000,
                          node2vec_price_per_hour=0.0)
        self.assertEqual(p["runtime_projections"]["node2vec_walk_generation_only"]["cost"], 0.0)
        for val in (float("nan"), float("inf"), -1.0, True):
            with self.subTest(val=val):
                with self.assertRaises(ValueError):
                    capacity_plan(node2vec_price_per_hour=val)

    def test_offline_cli_reproduces_same_counts(self):
        import os
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONPATH=str(root / "src"))
        r = subprocess.run([sys.executable, "-m", "pro_adherence.stage3_pilot_plan"],
                           cwd=root, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["graph"]["training_isolates"], 13596)
        self.assertIn("NO_INFERENCE", data["status"])


if __name__ == "__main__":
    unittest.main()
