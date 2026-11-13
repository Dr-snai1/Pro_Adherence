"""Public-model provenance: separate provider claims from locally checked small bytes."""
import json
from pathlib import Path
import re
import unittest

from pro_adherence.stage3_preflight import load_config

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"configs/stage3/model_preflight_pins.json"
EVIDENCE=ROOT/"configs/stage3/hf_pinned_file_evidence_20261111.json"

class Stage3HFPublicEvidenceTests(unittest.TestCase):
    def test_exact_inventory_without_false_weight_claim(self):
        a=json.loads(EVIDENCE.read_text(encoding="utf-8"))
        b=load_config(CONFIG)
        self.assertFalse(a["model_weights_downloaded"])
        self.assertFalse(a["model_weights_local_sha256_verified"])
        self.assertFalse(a["safe_runtime_verified"])
        self.assertFalse(a["owner_compute_authorized"])
        self.assertEqual(set(a["components"]),set(b["upstream_revisions"]))
        count=0
        for name,old in b["upstream_revisions"].items():
            entry=a["components"][name]
            self.assertEqual(entry["revision"],old["revision"])
            self.assertEqual(entry["repository"],old["repository"])
            self.assertEqual(set(entry["files"]),set(old["required_files"]))
            for filename,item in entry["files"].items():
                if filename.startswith("pytorch_"):
                    self.assertFalse(item["local_byte_sha256_verified"])
                    self.assertRegex(item["provider_lfs_sha256"],r"^[0-9a-f]{64}$")
                else:
                    count+=1
                    self.assertTrue(item["local_byte_sha256_verified"])
                    self.assertTrue(item["git_blob_verified"])
                    self.assertRegex(item["local_sha256"],r"^[0-9a-f]{64}$")
                    self.assertRegex(item["provider_git_blob"],r"^[0-9a-f]{40}$")
        self.assertEqual(count,9)
    def test_adapter_config_fingerprint_is_not_loader_readiness(self):
        a=json.loads(EVIDENCE.read_text(encoding="utf-8"))
        c=a["adapter_config_observed"]
        self.assertEqual((c["hidden_size"],c["reduction_factor"]),(768,16))
        self.assertEqual(c["model_class"],"BertAdapterModel")
        self.assertEqual(c["non_linearity"],"relu")
        self.assertTrue(c["output_adapter"])
        self.assertFalse(a["active_adapter_smoke_verified"])

if __name__=="__main__":
    unittest.main()
