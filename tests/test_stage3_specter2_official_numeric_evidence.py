"""Preserve one-time PUBLIC safe-vs-actual official SPECTER2 reference contract.

Offline only. No torch import, model downloads, private source text or inference.
"""
from pathlib import Path
import json
import unittest

ROOT=Path(__file__).resolve().parents[1]
OFFICIAL=ROOT/"configs/stage3/specter2_public_official_numeric_evidence.json"
SAFE=ROOT/"configs/stage3/specter2_public_safe_full_model_evidence.json"

class Specter2PublicOfficialReferenceEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o=json.loads(OFFICIAL.read_text(encoding="utf-8"))
        cls.s=json.loads(SAFE.read_text(encoding="utf-8"))

    def test_exact_public_model_adapters_and_reference_match(self):
        self.assertEqual(self.o["approved_base_sha256"],
            "801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc")
        self.assertEqual(self.o["approved_adapter_sha256"],
            "5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a")
        self.assertEqual(self.o["shape"],[3,768])
        self.assertEqual(self.o["max_abs_safe_vs_official"],0)
        self.assertGreaterEqual(self.o["min_cosine_safe_vs_official"],0.999999)
        self.assertEqual(self.o["actual_official_package"],"adapters==1.3.0")
        self.assertEqual(self.o["temporary_reference_transformers"],"4.57.6")
        self.assertIn("proximity",self.o["official_active_adapter"])
        self.assertTrue(self.o["gates"]["official_activated_proximity_public_synthetic_equivalence_verified"])

    def test_safe_full_model_numerics_and_token_loss(self):
        s=self.s
        self.assertEqual(s["model"]["adapter_layers_enabled"],12)
        self.assertEqual(s["model"]["synthetic_first_token_vectors_shape"],[3,768])
        self.assertEqual(s["model"]["max_abs_candidate_vs_independent_source_reference"],0)
        self.assertEqual(s["model"]["max_abs_repeated_same_process"],0)
        self.assertGreater(s["model"]["max_abs_adapter_vs_plain_bert"],0.001)
        stats=s["model"]["tokenization_audit_including_long_text"]
        self.assertEqual(len(stats),4)
        self.assertTrue(all(x["tokens_lost"]==0 for x in stats[:3]))
        self.assertGreater(stats[-1]["tokens_lost"],0)
        self.assertEqual(stats[-1]["encoded_tokens"],512)
        self.assertEqual(s["model"]["base"]["pretrained_base_tensors_loaded"],197)

    def test_old_reference_is_not_production_authorization(self):
        gates=self.o["gates"]
        self.assertTrue(gates["official_activated_proximity_public_synthetic_equivalence_verified"])
        for k in ("temporary_old_transformers_reference_is_approved_for_private_inference",
                  "permanent_secure_production_runtime_pinned_hash_lock_verified",
                  "private_specter2_inference_authorized",
                  "production_vectors_generated","publication_authorized","stage3_closed"):
            self.assertFalse(gates[k])
        for k in ("private_specter2_inference_authorized",
                  "production_vectors_generated","publication_authorized","stage3_closed"):
            self.assertFalse(self.s["gates"][k])

    def test_official_script_requires_preverified_public_sha_and_offline(self):
        script=(ROOT/"scripts/stage3_specter2_public_official_reference.py").read_text()
        self.assertIn("if os.environ.get('HF_HUB_OFFLINE')!='1'",script)
        self.assertIn("local_files_only=True",script)
        self.assertIn("set_active=True",script)
        self.assertIn("pytorch_adapter.bin",script)
        self.assertIn("max_abs>5e-5",script)
        self.assertNotIn("private_article",script)

if __name__=="__main__":
    unittest.main()
