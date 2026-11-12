"""Fully synthetic regression tests for the bounded node2vec p=q=1 smoke.

Does not read, require, or publish the private graph. Optional ML dependencies
are intentionally not made global project dependencies.
"""
import ast
import importlib.util
import json
from pathlib import Path
import unittest

try:
    import numpy as np
    import gensim  # noqa: F401
except ImportError:
    np = None


class Node2vecApprovedBackendContractTests(unittest.TestCase):
    """No optional ML packages or private corpus required."""
    def test_approved_settings_match_backend_explicit_keywords(self):
        root=Path(__file__).resolve().parents[1]
        cfg=json.loads((root/'configs/stage3/runtime_candidates.json').read_text(encoding='utf-8'))
        lane=cfg['lanes']['node2vec']
        self.assertEqual({k:lane['owner_approved_backend_settings'][k] for k in ('negative','sample')},
                         {'negative':5,'sample':0.001})
        self.assertEqual(lane['technical_skipgram_backend']['sg'],1)
        self.assertEqual(lane['technical_skipgram_backend']['hs'],0)
        self.assertEqual(lane['scientific_backend_choices_pending'],[])
        self.assertFalse(cfg['owner_compute_permission'])
        self.assertIsNone(lane['exact_runtime_lock_sha256'])
        self.assertFalse(lane['dependency_resolution_verified'])
        self.assertFalse(lane['full_scale_ram_verified'])
        self.assertFalse(lane['full_scale_time_verified'])
        self.assertFalse(lane['production_embeddings_generated'])
        tree=ast.parse((root/'scripts/stage3_node2vec_cpu_smoke.py').read_text(encoding='utf-8'))
        consts={a.targets[0].id:a.value.value for a in tree.body
                if isinstance(a,ast.Assign) and len(a.targets)==1
                and isinstance(a.targets[0],ast.Name) and isinstance(a.value,ast.Constant)}
        train=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='train')
        calls=[n for n in ast.walk(train) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
               and n.func.id=='Word2Vec']
        self.assertEqual(len(calls),1)
        args={kw.arg:kw.value.id for kw in calls[0].keywords if isinstance(kw.value,ast.Name)}
        for name,symbol,expected in [('negative','NEGATIVE',5),('sample','SAMPLE',0.001),
                                     ('sg','SG',1),('hs','HS',0)]:
            self.assertEqual(args[name],symbol)
            self.assertEqual(consts[symbol],expected)


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

    def test_repeatable_walk_stream_synthetic_training(self):
        m=self.m
        offsets=np.array([0,1,3,4,4],dtype=np.int64)
        adjacent=np.array([1,0,2,1],dtype=np.int32)
        starts=np.array([0,1,2],dtype=np.int32)
        stream=m.RepeatableWalkCorpus(starts,offsets,adjacent,m.SEED)
        expected=m.walk_digest(m.walk_generator(starts,offsets,adjacent,m.SEED))
        self.assertEqual(m.walk_digest(stream),expected)
        self.assertEqual(m.walk_digest(stream),expected)
        self.assertEqual(sum(1 for _ in stream),30)
        one=m.train(stream,m.SEED)
        two=m.train(stream,m.SEED)
        self.assertEqual(set(one.wv.index_to_key),{'0','1','2'})
        self.assertNotIn('3',one.wv)
        self.assertEqual(m.vectors_digest(one),m.vectors_digest(two))
        self.assertEqual((one.sg,one.hs,one.negative,one.sample),(1,0,5,0.001))


if __name__=='__main__': unittest.main()
