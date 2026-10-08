import copy
import importlib.util
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator, RefResolver, FormatChecker

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("computation_signature", ROOT/"src/pro_adherence/computation_signature.py")
c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
def load(path): return json.loads((ROOT/path).read_text())
lineage=load("contracts/manifests/minimal_lineage.example.json")
asset=load("contracts/examples/model_compute_asset.example.json")
model=lineage["model_refs"][0]
schema=load("contracts/schemas/provenance.schema.json")
store={x["$id"]:x for x in (schema,load("contracts/schemas/ids.schema.json"),load("contracts/schemas/access-license.schema.json"))}
v=Draft202012Validator(schema, resolver=RefResolver.from_schema(schema,store=store), format_checker=FormatChecker())
class IdentityTests(unittest.TestCase):
    def test_model_and_schema(self):
        self.assertEqual(c.model_identity_hash(model),"2e75c08ef87dbe230d94964dbaa8117bb44c9269ecc4bc1b1f82712e75f2cdaf")
        self.assertTrue(v.is_valid(model))
        self.assertTrue(v.is_valid(asset))
        self.assertTrue(c.validate_compute_asset(asset,[model],lineage["artifacts"],lineage["config_refs"]))
    def test_nonmodel(self):
        a=copy.deepcopy(asset)
        a["model_ref_id"]=None
        a["computation_signature"]["model_identity_hash"]=None
        a["computation_signature"]["digest"]=c.computation_digest(a["computation_signature"])
        self.assertTrue(v.is_valid(a))
        self.assertTrue(c.validate_compute_asset(a,[]))
    def test_committed_nonmodel_fixture(self):
        a=load("contracts/examples/nonmodel_compute_asset.example.json")
        self.assertTrue(v.is_valid(a))
        self.assertTrue(c.validate_compute_asset(a,[]))
    def test_digest_only_revision_only(self):
        for changes in (dict(immutable_revision=None,identity_namespace=None,identity_key=None),dict(digest=None)):
            m=dict(model,**changes)
            self.assertTrue(v.is_valid(m))
            self.assertRegex(c.model_identity_hash(m),r"^[0-9a-f]{64}$")
    def test_material_changes(self):
        old=c.model_identity_hash(model)
        original_signature=c.computation_digest(asset["computation_signature"])
        for field,value in (("digest","a"*64),("immutable_revision","new-immutable-revision")):
            modified=dict(model,**{field:value})
            new=c.model_identity_hash(modified)
            self.assertNotEqual(new,old)
            sig=dict(asset["computation_signature"],model_identity_hash=new)
            self.assertNotEqual(c.computation_digest(sig),original_signature)
    def test_name_only(self):
        self.assertEqual(c.model_identity_hash(dict(model,model_name="renamed")),c.model_identity_hash(model))
    def test_missing_identity_and_bad_digests(self):
        for replacement in (None,"f"*64):
            a=copy.deepcopy(asset)
            a["computation_signature"]["model_identity_hash"]=replacement
            with self.assertRaises(c.SignatureError):
                c.validate_compute_asset(a,[model])
        a=copy.deepcopy(asset)
        a["computation_signature"]["digest"]="0"*64
        with self.assertRaises(c.SignatureError):
            c.validate_compute_asset(a,[model])
    def test_invalid_revision_and_empty_model(self):
        for changes in (dict(identity_namespace=None),dict(identity_key=None),dict(digest=None,immutable_revision=None)):
            m=dict(model,**changes)
            self.assertFalse(v.is_valid(m))
            with self.assertRaises(c.SignatureError):
                c.model_identity_hash(m)
if __name__=="__main__": unittest.main()
