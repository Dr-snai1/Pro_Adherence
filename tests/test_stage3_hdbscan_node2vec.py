"""Source-free unit tests: HDBSCAN parameter/metric and independent null policy."""
import unittest
import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.metrics import adjusted_rand_score

class TestHdbscanSourceFree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng=np.random.default_rng(20261031)
        x=np.r_[rng.normal(loc=[-4,0],scale=0.07,size=(60,2)),
                rng.normal(loc=[4,0],scale=0.07,size=(60,2))]
        cls.x=x.astype(np.float32)
    def test_two_distinct_dense_modes(self):
        m=HDBSCAN(min_cluster_size=10,min_samples=5,metric='euclidean',copy=True)
        lab=m.fit_predict(self.x)
        self.assertGreaterEqual(len(set(lab)-{-1}),2)
        self.assertEqual(len(lab),120)
        self.assertTrue(np.all(np.isfinite(m.probabilities_)))
    def test_determinism_same_input(self):
        a=HDBSCAN(min_cluster_size=10,min_samples=5,copy=True).fit_predict(self.x)
        b=HDBSCAN(min_cluster_size=10,min_samples=5,copy=True).fit_predict(self.x)
        self.assertTrue(np.array_equal(a,b))
    def test_label_invariance_adjusted_rand(self):
        self.assertAlmostEqual(adjusted_rand_score([0,0,1,1,-1],[9,9,3,3,0]),1.0)
    def test_unit_euclidean_cosine_monotonicity(self):
        rng=np.random.default_rng(31);vectors=rng.normal(size=(10,7));vectors=vectors/np.linalg.norm(vectors,axis=1,keepdims=True)
        x=vectors[0];dist=np.linalg.norm(vectors[1:]-x,axis=1);cos=1-vectors[1:]@x
        self.assertTrue(np.array_equal(np.argsort(dist),np.argsort(cos)))
        self.assertTrue(np.allclose(dist**2,2*cos,atol=1e-12))
    def test_structural_missing_vs_noise(self):
        statuses=['ready','missing_structural','ready'];hdbscan_noise=[True,None,False]
        self.assertEqual(sum(x=='missing_structural' for x in statuses),1)
        self.assertEqual(sum(x is True for x in hdbscan_noise),1)
        self.assertNotEqual(hdbscan_noise[1],True)

if __name__=='__main__':unittest.main(verbosity=2)
