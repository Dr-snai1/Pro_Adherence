"""Pure/synthetic Hugging Face metadata audit tests; no internet or model load."""
import unittest
from copy import deepcopy
from pro_adherence.stage3_preflight import Stage3PreflightError
from pro_adherence.stage3_hf_provenance import (
    audit_component, audit_metadata_snapshot, metadata_url,
)
from pro_adherence.stage3_preflight import load_config
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "configs/stage3/model_preflight_pins.json"


def synthetic(repo, revision, filenames):
    return {"sha": revision, "siblings": [
        {"rfilename": name, "size": 12,
         "lfs": {"sha256": "a" * 64} if name.startswith("pytorch_") else None}
        for name in filenames
    ]}


class HfProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(CONFIG)
        self.snapshots = {
            key: synthetic(item["repository"], item["revision"], item["required_files"])
            for key, item in self.cfg["upstream_revisions"].items()
        }

    def test_all_three_and_no_byte_claims(self):
        r = audit_metadata_snapshot(self.cfg, self.snapshots)
        self.assertFalse(r["model_bytes_readback_verified"])
        self.assertFalse(r["model_load_executed"])
        self.assertEqual(len(r["components"]), 3)
        for component in r["components"].values():
            self.assertFalse(component["ready_for_compute"])
            for f in component["required_files"].values():
                self.assertFalse(f["local_content_sha256_verified"])

    def test_mismatch_and_missing_weight_lfs_are_blockers(self):
        s = self.cfg["upstream_revisions"]["specter2_proximity"]
        bad = deepcopy(self.snapshots["specter2_proximity"])
        bad["sha"] = "b" * 40
        with self.assertRaisesRegex(Stage3PreflightError, "revision mismatch"):
            audit_component(s, bad)
        bad = deepcopy(self.snapshots["specter2_proximity"])
        bad["siblings"][-1]["lfs"] = None
        with self.assertRaisesRegex(Stage3PreflightError, "model weight LFS"):
            audit_component(s, bad)
        bad = deepcopy(self.snapshots["specter2_proximity"])
        bad["siblings"].append(deepcopy(bad["siblings"][0]))
        with self.assertRaisesRegex(Stage3PreflightError, "duplicate"):
            audit_component(s, bad)

    def test_metadata_url_cannot_point_to_binary_or_non_hf(self):
        s = self.cfg["upstream_revisions"]["pubmedbert"]
        u = metadata_url(s["repository"], s["revision"])
        self.assertIn("/api/models/", u)
        self.assertNotIn("/resolve/", u)
        for repo in ("../../evil", "evil.com/../../x", "a/https://evil.com", "a"):
            with self.subTest(repo=repo):
                with self.assertRaises(Stage3PreflightError):
                    metadata_url(repo, s["revision"])


if __name__ == "__main__":
    unittest.main()
