"""Offline-only safety checks for approved Stage3 57,204 SPECTER2 CPU checkpoint runner."""
import ast
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
FULL=ROOT/"scripts/stage3_specter2_private_full_cpu.py"
AUDIT=ROOT/"scripts/stage3_specter2_private_full_independent_audit.py"
class FullSpecter2Contracts(unittest.TestCase):
    def test_frozen_approved_scientific_contract_and_owner_gate(self):
        s=FULL.read_text()
        ast.parse(s)
        for token in (
            "COHORT, DIM, MAX_TOKENS, SHARD_ROWS = 57204, 768, 512, 1000",
            "APPROVED_FULL_ARCHIVE_SHA='cc60cefdaa62a60712425b0f1ea1719338ec4250ec8bcaf1fd465329c677395e'",
            "APPROVED_BASE_SHA='801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc'",
            "APPROVED_ADAPTER_SHA='5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'",
            "if not args.owner_full_scope", "if not __debug__", "HF_HUB_OFFLINE",
            "last_hidden_state[:,0,:]", "max_length=MAX_TOKENS",
            "'raw.float32.npy'", "'raw_l2_norm.float64.npy'", "'unit.float32.npy'",
            "'publication_authorized':False", "'stage3_closed':False",
        ):self.assertIn(token,s)
        self.assertIn("validate_existing(dest,ix,start,batchrows)",s)
        self.assertIn("sum(x['report']['rows'] for x in shard_reports)!=COHORT",s)
    def test_independent_auditor_does_not_import_model_or_publish_rows(self):
        s=AUDIT.read_text()
        ast.parse(s)
        for token in ("z.testzip()", "file_sha(path)", "np.load", "'text_sha256'",
                      "'canonical_article_id'","'tokens_lost'",
                      "'FULL_57204_MANIFEST.private.json'"):self.assertIn(token,s)
        self.assertNotIn("import torch",s)
        self.assertNotIn("from_pretrained",s)
if __name__=="__main__":unittest.main()
