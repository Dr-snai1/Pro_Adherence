"""Tiny synthetic, no-network regression checks for executed PubMedBERT chunk policy."""
from pathlib import Path
import importlib.util
import unittest
MODULE=Path(__file__).resolve().parents[1]/"scripts"/"stage3_p1_pubmedbert_local.py"
spec=importlib.util.spec_from_file_location("stage3_p1_pubmedbert_local",MODULE)
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class FakeTokenizer:
    cls_token_id=101
    sep_token_id=102
    def encode(self,s,add_special_tokens=False):
        assert not add_special_tokens
        return [200+ord(c)%50 for c in s if not c.isspace()]

class Stage3P1PubmedBertContractTests(unittest.TestCase):
    def test_title_only_exact_bytes_without_abstract(self):
        r={"article_id":"a1","text_state":"title_only","title":"Healthy living","abstract":None}
        chunks,forced,fallback,t,a=runner.prepare_chunks(r,FakeTokenizer())
        self.assertEqual((len(chunks),forced,fallback,a),(1,0,False,0))
        self.assertEqual(chunks[0]["content_tokens"],t)
        self.assertEqual(chunks[0]["ids"][0],101)
        self.assertEqual(chunks[0]["ids"][-1],102)
    def test_sentence_aware_long_abstract_no_loss_or_repeat(self):
        text="A result. "*400
        row={"article_id":"a2","text_state":"title_abstract","title":"Test","abstract":text}
        chunks,forced,fallback,t,a=runner.prepare_chunks(row,FakeTokenizer())
        self.assertGreater(len(chunks),1)
        self.assertEqual(forced,0)
        self.assertFalse(fallback)
        self.assertEqual(sum(c["content_tokens"] for c in chunks),t+a)
        self.assertTrue(all(len(c["ids"])<=512 for c in chunks))
        self.assertEqual(chunks[0]["ids"][0],101)
        self.assertTrue(all(c["ids"][0]==101 and c["ids"][-1]==102 for c in chunks))
    def test_wrong_input_status_does_not_infer(self):
        with self.assertRaises(ValueError):
            runner.prepare_chunks({"article_id":"a3","text_state":"requires_source_resolution","title":"Title","abstract":"Abstract"},FakeTokenizer())
if __name__=="__main__":
    unittest.main()
