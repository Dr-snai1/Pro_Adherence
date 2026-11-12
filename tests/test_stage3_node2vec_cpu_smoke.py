"""Fully synthetic regression tests for the bounded node2vec p=q=1 smoke.

Does not read, require, or publish the private graph. Optional ML dependencies
are intentionally not made global project dependencies.
"""
import importlib.util
from pathlib import Path
import unittest

try:
    import numpy as np
    import gensim  # noqa: F401
except ImportError:
    np = None


@unittest.skipIf(np is None, 'Optional node2vec research CPU environment not present')
class Node2vecCpuSmokeSyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module_path=(Path(__file__).resolve().parents[1] / 'scripts' / 'stage3_node2vec_cpu_smoke.py')
        spec=importlib.util.spec_from_file_location('node2vec_smoke',module_path)
        cls.m=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def test_exact_degree_strata_starts_and_seed(self):
        degrees=np.array([1]*120+[4]*120+[10]*120+[34]*120,dtype=np.int32)
        a,b=self.m.choose_starts(degrees)
        c,d=self.m.choose_starts(degrees)
        np.testing.assert_array_equal(a,c)
        self.assertEqual(b,[120]*4)
        self.assertEqual(d,b)
        self.assertEqual(len(a),436)
        self.assertEqual(len(set(a.tolist())),436)
        self.assertEqual([sum(a<120),sum((a>=120)&(a<240)),sum((a>=240)&(a<360)),sum(a>=360)],[109]*4)

    def test_uniform_first_order_walks_and_train_seed_stability(self):
        offsets=np.array([0,1,3,4,4],dtype=np.int64)
        adjacent=np.array([1,0,2,1],dtype=np.int32)
        starts=np.array([1,2],dtype=np.int32)
        m=self.m
        a=list(m.walk_generator(starts,offsets,adjacent,m.SEED))
        b=list(m.walk_generator(starts,offsets,adjacent,m.SEED))
        c=list(m.walk_generator(starts,offsets,adjacent,m.SEED+1))
        self.assertEqual(a,b)
        self.assertNotEqual(a,c)
        self.assertEqual(len(a),20)
        self.assertTrue(all(len(w)==40 and '3' not in w for w in a))
        edge_set={(0,1),(1,0),(1,2),(2,1)}
        self.assertTrue(all((int(x),int(y)) in edge_set for w in a for x,y in zip(w,w[1:])))
        model=m.train(a,m.SEED)
        model_repeated=m.train(a,m.SEED)
        self.assertEqual(m.vectors_digest(model),m.vectors_digest(model_repeated))
        self.assertEqual(model.wv.vector_size,128)
        self.assertTrue(np.isfinite(model.wv.vectors).all())


if __name__=='__main__': unittest.main()
