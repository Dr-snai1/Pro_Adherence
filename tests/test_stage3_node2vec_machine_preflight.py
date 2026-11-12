"""Synthetic/read-only resource contract; no private graph and NO training."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/stage3_node2vec_cpu_machine_preflight.py"

def load():
    spec = importlib.util.spec_from_file_location("node2vec_machine_preflight", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class Node2vecMachineReadOnlyTests(unittest.TestCase):
    def test_no_training_or_walk_generation_in_preflight_source(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        called = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertNotIn("train", called)
        self.assertNotIn("walk_generator", called)
        self.assertNotIn("fit", called)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertNotIn("RepeatableWalkCorpus", names)
        self.assertIn("estimate_memory", called)

    def test_exact_graph_hash_mismatch_fails_closed_without_parsing(self):
        import tempfile
        mod = load()
        with tempfile.TemporaryDirectory() as temp:
            fake = Path(temp) / "not-private-graph.zip"
            fake.write_bytes(b"synthetic graph ZIP intentionally invalid")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                mod.verify_graph_archive(fake)

    def test_cgroup_read_is_passive_and_reports_nonnegative_capacity(self):
        result = load().cgroup_memory()
        self.assertIn(result["source"], ("cgroup_v2", "physical_or_unknown"))
        if result["source"] == "cgroup_v2":
            self.assertGreater(result["limit_bytes"], 0)
            self.assertGreaterEqual(result["current_bytes"], 0)
            self.assertGreaterEqual(result["available_to_cgroup_bytes"], 0)

    def test_has_no_hidden_compute_authorization_defaults(self):
        text = SOURCE.read_text(encoding="utf-8")
        for blocked in (
            '"owner_full_training_authorized": False',
            '"full_runtime_identity_verified_on_target": False',
            '"peak_RSS_safety_guaranteed": False',
            '"production_embeddings_generated": False',
            '"publication_authorized": False',
        ):
            self.assertIn(blocked, text)

    def test_provider_hashed_wheels_have_five_explicit_sha256(self):
        import re
        p = ROOT / "configs/stage3/node2vec_cpu_cp313_linux_x86_64.requirements.txt"
        lines = p.read_text(encoding="utf-8").splitlines()
        packages = re.findall(r"^([\w-]+)==([\d.]+) --hash=sha256:([a-f0-9]{64})$", "\n".join(lines), flags=re.M)
        self.assertEqual(len(packages), 5)
        self.assertEqual({p[0] for p in packages}, {"gensim", "numpy", "scipy", "smart-open", "wrapt"})

if __name__ == "__main__":
    unittest.main()
