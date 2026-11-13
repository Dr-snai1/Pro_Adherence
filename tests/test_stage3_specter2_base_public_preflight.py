"""No-network, no-ML, no-private-corpus tests for public SPECTER2 base identity."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts"/"stage3_specter2_base_public_preflight.py"
SPEC=importlib.util.spec_from_file_location("specter2_public_base",SOURCE)
base=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

class SPECTER2PublicBaseTests(unittest.TestCase):
    def fixture(self):
        return {"sha":base.REV,"siblings":[
            {"rfilename":name,**({"lfs":{"sha256":base.EXPECTED_WEIGHT_SHA},"size":440000000}
                                if name=="pytorch_model.bin" else {})}
            for name in base.FILES]}
    def test_metadata_only_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"metadata.json"
            p.write_text(json.dumps(self.fixture()),encoding="utf-8")
            x=base.audit(p)
            self.assertEqual(x["status"],"HF_METADATA_ONLY_MODEL_BYTES_PENDING")
            self.assertFalse(x["gates"]["approved_public_base_bytes_verified"])
            self.assertFalse(x["gates"]["numeric_equivalence_to_official_adapter"])
            self.assertFalse(x["gates"]["private_specter2_inference_authorized"])
            self.assertFalse(x["gates"]["production_vectors_created"])
            self.assertFalse(x["pickle_or_model_executed"])
            self.assertIsNone(x["files"])

    def test_mutated_revision_weight_lfs_or_missing_member_fails(self):
        fixture=self.fixture()
        for change in ("revision","sha","missing"):
            obj=json.loads(json.dumps(fixture))
            if change=="revision":obj["sha"]="x"*40
            elif change=="sha":next(x for x in obj["siblings"] if x["rfilename"]=="pytorch_model.bin")["lfs"]["sha256"]="f"*64
            else:obj["siblings"]=obj["siblings"][:-1]
            with self.subTest(change=change),self.assertRaises(base.Rejected):
                base.metadata_check(obj)

    def test_base_architecture_rejects_drift(self):
        obj={"model_type":"bert","hidden_size":768,"num_hidden_layers":12,
             "num_attention_heads":12,"intermediate_size":3072,
             "max_position_embeddings":512,"vocab_size":31090,
             "layer_norm_eps":1e-12,"hidden_act":"gelu"}
        base.check_base_config(obj)
        for key in obj:
            changed=dict(obj)
            changed[key]="768" if isinstance(obj[key],int) else 123
            with self.subTest(key=key),self.assertRaises(base.Rejected):
                base.check_base_config(changed)

    def test_untrusted_bytes_fail_before_deserialization(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/"metadata.json").write_text(json.dumps(self.fixture()))
            for filename in base.FILES:(p/filename).write_bytes(b"bad synthetic bytes")
            with self.assertRaisesRegex(base.Rejected,"SHA256"):
                base.audit(p/"metadata.json",p)
        src=SOURCE.read_text()
        self.assertNotIn("torch.load",src)
        self.assertNotIn("pickle.load",src)
        self.assertNotIn("from_pretrained",src)

if __name__=="__main__":unittest.main()
