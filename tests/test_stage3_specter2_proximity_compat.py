"""Synthetic math regression for experimental SPECTER2 adapter candidate.

No full SPECTER2 pretrained base or private article data is used. The exact
numerical equivalence of this candidate to upstream Adapters remains pending.
"""
import importlib.util
from pathlib import Path
import unittest

try:
    import torch
    from torch import nn
    import torch.nn.functional as F
except ImportError:
    torch=None

SOURCE=Path(__file__).resolve().parents[1]/'src'/'pro_adherence'/'stage3_specter2_proximity_compat.py'

@unittest.skipIf(torch is None,'Optional public torch CPU runtime unavailable')
class CandidateAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('specter2_candidate',SOURCE)
        cls.m=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @staticmethod
    def fake_weights():
        rng=torch.Generator().manual_seed(101)
        return {k:torch.randn(shape,generator=rng,dtype=torch.float32)*0.02
                for k,shape in CandidateAdapterTests.m.expected_shapes().items()}

    def test_key_and_shape_contract(self):
        self.assertTrue(self.m.EXPERIMENTAL_NOT_VALIDATED)
        expected=self.m.expected_shapes()
        self.assertEqual(len(expected),48)
        self.assertEqual(len({k.split('.output.')[0] for k in expected}),12)
        self.assertEqual(sum(k.endswith('.weight') for k in expected),24)

    def test_pre_and_post_layernorm_algebra_on_synthetic_ffn(self):
        torch.manual_seed(103)
        class SyntheticOutput(nn.Module):
            def __init__(self):
                super().__init__()
                self.dense=nn.Linear(768,768)
                self.dropout=nn.Dropout(0.0)
                self.LayerNorm=nn.LayerNorm(768,eps=1e-12)
        base=SyntheticOutput().eval()
        tensors=self.fake_weights()
        candidate=self.m.CandidateBertOutputAdapter(base,tensors,3)
        x=torch.randn(2,3,768)
        residual=torch.randn(2,3,768)
        with torch.no_grad():
            actual=candidate(x,residual)
            ffn=base.dropout(base.dense(x))
            first=base.LayerNorm(ffn+residual)
            prefix='bert.encoder.layer.3.output.adapters.[PRX].'
            down=F.linear(first,tensors[prefix+'adapter_down.0.weight'],tensors[prefix+'adapter_down.0.bias'])
            up=F.linear(F.relu(down),tensors[prefix+'adapter_up.weight'],tensors[prefix+'adapter_up.bias'])
            expected=base.LayerNorm((up+ffn)+residual)
        self.assertEqual(actual.shape,(2,3,768))
        self.assertTrue(torch.isfinite(actual).all().item())
        self.assertLessEqual((actual-expected).abs().max().item(),1e-6)
        self.assertTrue(all(not p.requires_grad for p in candidate.parameters()))
        self.assertTrue(candidate.training is False)

    def test_unsafe_training_or_bad_layer_rejected(self):
        base=nn.Module()
        base.dense=nn.Linear(768,768);base.dropout=nn.Dropout(0.0);base.LayerNorm=nn.LayerNorm(768)
        w=self.fake_weights()
        with self.assertRaises(ValueError):self.m.CandidateBertOutputAdapter(base,w,12)
        candidate=self.m.CandidateBertOutputAdapter(base,w,0)
        candidate.train()
        with self.assertRaisesRegex(RuntimeError,'eval-only'):
            candidate(torch.zeros(1,1,768),torch.zeros(1,1,768))

if __name__=='__main__':unittest.main()
