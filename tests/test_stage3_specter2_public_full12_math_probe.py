"""No-ML regression checks for pinned public SPECTER2 base and 12-layer evidence."""
from __future__ import annotations
import ast
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/"configs/stage3/specter2_public_base_evidence.json").read_text())
PROBE=json.loads((ROOT/"configs/stage3/specter2_public_full12_synthetic_math_evidence.json").read_text())
SCRIPT=ROOT/"scripts/stage3_specter2_public_full12_math_probe.py"

class Specter2EvidenceContracts(unittest.TestCase):
    def test_all_six_base_bytes_verified_and_no_inference(self):
        self.assertEqual(BASE["base_revision"],"3447645e1def9117997203454fa4495937bfbd83")
        self.assertEqual(BASE["files"]["pytorch_model.bin"]["sha256"],
                         "801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc")
        self.assertEqual(len(BASE["files"]),6)
        self.assertEqual(sum(f["bytes"] for f in BASE["files"].values()),440686472)
        self.assertTrue(BASE["checks"]["all_six_file_sha_bytes_verified"])
        self.assertFalse(BASE["checks"]["unpickle_or_model_inference_executed"])
        for field in ("official_adapter_active_numeric_equivalence_verified",
                      "private_specter2_inference_authorized","production_vectors_generated","stage3_closed"):
            self.assertFalse(BASE["limitations"][field])

    def test_full12_real_adapter_math_is_not_official_inference(self):
        self.assertEqual(PROBE["adapter_layers_tested"],12)
        self.assertEqual(PROBE["max_abs_vs_independent_source_equation"],0)
        self.assertGreater(PROBE["min_adapter_activation_delta_vs_plain_bert_output"],0)
        self.assertTrue(PROBE["actual_pinned_weights_loaded_with_weights_only"])
        self.assertEqual(PROBE["adapter_sha256"],
                         "5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a")
        self.assertFalse(any(PROBE["gates"].values()))
        self.assertIn("NOT_OFFICIAL_EQUIVALENCE",PROBE["status"])

    def test_probe_is_synthetic_and_uses_exact_weight_sha_before_loading(self):
        src=SCRIPT.read_text(encoding="utf-8")
        ast.parse(src)
        self.assertIn("pinned_weights_only(weights)",src)
        self.assertIn("torch.manual_seed(20261113)",src)
        self.assertIn("real_base_weights_loaded",src)
        self.assertNotIn("from_pretrained",src)
        self.assertNotIn("private_graph",src)
        self.assertNotIn("pandas",src)

if __name__=="__main__":unittest.main()
