"""Public synthetic-only contract for owner-authorized full node2vec runner.

The tests NEVER load private graph, generate full walks or train Word2Vec.
"""
import ast
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage3_node2vec_cpu_full_local.py"

class Node2vecFullRunnerPublicContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.constants = {}
        for node in cls.tree.body:
            if isinstance(node, ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                if isinstance(node.value,ast.Constant):
                    cls.constants[node.targets[0].id]=node.value.value

    def test_approved_graph_and_backend_are_fixed(self):
        for k,v in {"GRAPH_SHA":"33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c",
                    "SEED":20261031,"N_NODES":57204,"N_EDGES":328298,"N_ISOLATES":13596,
                    "WALKS_PER_NODE":10,"WALK_LENGTH":40,"DIM":128,
                    "WINDOW":10,"EPOCHS":1,"NEGATIVE":5,"SAMPLE":0.001}.items():
            self.assertEqual(self.constants[k],v)
        self.assertIn("workers=1",self.source)
        self.assertIn("sorted_vocab=1",self.source)
        self.assertIn("hashfxn=fixed_hash",self.source)

    def test_must_fail_closed_and_no_implicit_publication(self):
        self.assertIn("if not __debug__",self.source)
        self.assertIn("mem_cap-max(512*1024*1024,mem_cap//10)",self.source)
        self.assertIn("fail('TRAINED VOCABULARY IS NOT FULL 43608 NONISOLATED NODES')",self.source)
        self.assertIn("'publication_authorized':False",self.source)
        self.assertIn("'stage_gate_authorized':False",self.source)
        self.assertIn("'pr_merge_authorized':False",self.source)
        self.assertIn("if temp.exists() or outzip.exists()",self.source)
        self.assertIn("z.testzip()",self.source)

    def test_all_three_vector_artifacts_and_full_roster(self):
        self.assertIn("'raw.float32.npy'",self.source)
        self.assertIn("'raw_l2_norm.float64.npy'",self.source)
        self.assertIn("'unit.float32.npy'",self.source)
        self.assertIn("'article_status.private.jsonl.gz'",self.source)
        self.assertIn("'missing_structural'",self.source)
        self.assertIn("'model_identity_hash'",self.source)
        self.assertIn("'walk_passes'",self.source)
        self.assertIn("np.allclose(raw,unit*norm",self.source)

if __name__=="__main__":
    unittest.main()
