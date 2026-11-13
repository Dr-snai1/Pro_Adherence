"""Static/synthetic-only contract: incremental SPECTER2 batch 009–013 auditor.

No access to private article records or model inference in CI.
"""
from pathlib import Path
import ast
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"scripts/stage3_specter2_partial_batch_independent_audit.py"

class IndependentPartialSpecter2Tests(unittest.TestCase):
    def test_source_only_assertions_and_no_torch(self):
        source=SRC.read_text(encoding="utf-8")
        ast.parse(source)
        for text in (
            "def audit_index(", "def source_rows(", "def bytes_sha(",
            "EXPECTED_INPUT=", "EXPECTED_MEMBER=", "EXPECTED_BASE=",
            "EXPECTED_ADAPTER=", "EXPECTED_RUNTIME=",
            "np.load(", "allow_pickle=False", "z.testzip() is None",
            "record['canonical_article_id']==src['article_id']",
            "record['status']=='ready'",
            "manifest['shard_index']==i", "record['tokens_lost']==max(0,record['untruncated_tokens']-512)",
        ):
            self.assertIn(text,source)
        for forbidden in ("import torch", "import transformers", "from_pretrained(", "requests.get("):
            self.assertNotIn(forbidden,source)
    def test_only_expected_sequential_block_without_model_computations(self):
        source=SRC.read_text(encoding="utf-8")
        self.assertIn("9<=args.start<=args.stop<=13",source)
        self.assertIn("range(args.start,args.stop+1)",source)
        self.assertIn("57204",source)
        self.assertIn("1000*i",source)
        self.assertNotIn("torch.inference_mode",source)
        self.assertNotIn("last_hidden_state",source)

if __name__=="__main__":
    unittest.main()
