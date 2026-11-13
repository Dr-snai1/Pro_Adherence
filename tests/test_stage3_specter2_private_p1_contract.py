"""Synthetic/static safety contracts for private Stage 3 SPECTER2 P1 CPU lane.

No private records, graph, public 440MB weights or inference in CI.
"""
import ast
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
SAMPLE=ROOT/"scripts/stage3_specter2_private_p1_sample_local.py"
RUNNER=ROOT/"scripts/stage3_specter2_private_p1_cpu.py"
AUDIT=ROOT/"scripts/stage3_specter2_private_p1_independent_audit.py"

class Stage3Specter2PrivatePilotContracts(unittest.TestCase):
    def test_pilot_fixed_scope_and_owner_gate(self):
        s=RUNNER.read_text(encoding="utf-8")
        tree=ast.parse(s)
        names={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}
        self.assertIn("APPROVED_SAMPLE_SHA",names)
        self.assertIn("SMOKE_COUNT",names)
        self.assertIn("P1_COUNT",names)
        self.assertIn("owner_p1_scope",s)
        for item in (
            "APPROVED_INPUT_ZIP_SHA='cc60cefdaa62a60712425b0f1ea1719338ec4250ec8bcaf1fd465329c677395e'",
            "APPROVED_SAMPLE_SHA='b37128da2ef9fc6f15834c48a537b4ddb9ae7475dafcf7e0bb7fec586737d23b'",
            "APPROVED_GRAPH_SHA='33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c'",
            "P1_COUNT,SMOKE_COUNT,DIM,MAX_TOKENS,BATCH=1000,64,768,512,2",
            "if not args.owner_p1_scope",
            "if not __debug__",
            "def choose_64(",
            "def numeric(",
            "def lock_check(",
            "torch.inference_mode()",
            "'full_57204_production_vectors_created':False",
            "'stage3_closed':False",
            "'publication_authorized':False",
        ):
            self.assertIn(item,s)
        self.assertNotIn("def full_57204",s)
        self.assertNotIn("adapters.AutoAdapterModel",s)

    def test_offline_disallows_research_text_in_public_builds(self):
        s=RUNNER.read_text(encoding="utf-8")
        self.assertIn("HF_HUB_OFFLINE",s)
        self.assertIn("TRANSFORMERS_OFFLINE",s)
        self.assertIn("pinned_weights_only",s)
        self.assertIn("verify_public_files",s)
        self.assertIn("max_length=MAX_TOKENS",s)
        self.assertIn("return_token_type_ids=False",s)
        self.assertIn("no overwrite",s)
        self.assertIn("STAGE3",SAMPLE.read_text())
        self.assertIn("Pro",str(ROOT))
        ast.parse(SAMPLE.read_text(encoding="utf-8"))

    def test_independent_auditor_never_runs_inference(self):
        s=AUDIT.read_text(encoding="utf-8")
        ast.parse(s)
        self.assertIn("np.load",s)
        self.assertIn("zipfile.ZipFile",s)
        self.assertIn("SRC_SHA='b37128da2ef9fc6f15834c48a537b4ddb9ae7475dafcf7e0bb7fec586737d23b'",s)
        self.assertIn("all_finite_norms_reconstruction",s)
        self.assertNotIn("import torch",s)
        self.assertNotIn("from_pretrained",s)

if __name__=="__main__":
    unittest.main()
