"""Source-free numerical equivalence tests for 64-bit disk-backed HDBSCAN MST."""
import unittest,tempfile
from pathlib import Path
import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.cluster._hdbscan.hdbscan import tree_to_labels
from sklearn.metrics import adjusted_rand_score
from stage3_full_semantic_hdbscan_dense_exact import compute_single_linkage

class TestExactDiskHDBSCAN(unittest.TestCase):
 def test_equal_sklearn_exact_eom_labels_probabilities_8d_and_20d(self):
  rng=np.random.default_rng(98)
  for n in (80,170,370):
   for dim in (8,20):
    x=rng.normal(size=(n,dim));x/=np.linalg.norm(x,axis=1)[:,None]
    with tempfile.TemporaryDirectory() as d:
     tree=compute_single_linkage(np.asarray(x,dtype=np.float64),Path(d)/'D.tmp',min_samples=5,block=64)
     self.assertFalse((Path(d)/'D.tmp').exists(),'Scratch matrix not removed')
     for mcs in (15,24):
      lab,pr=tree_to_labels(tree,mcs,cluster_selection_method='eom',allow_single_cluster=False,cluster_selection_epsilon=0,max_cluster_size=None)
      sk=HDBSCAN(min_samples=5,min_cluster_size=mcs,metric='euclidean',copy=True).fit(x)
      self.assertEqual(adjusted_rand_score(lab,sk.labels_),1.0,(n,dim,mcs))
      self.assertLess(np.max(np.abs(np.sort(pr)-np.sort(sk.probabilities_))),1e-7)
 def test_nonunit_vectors_as_well(self):
  rng=np.random.default_rng(988);x=rng.normal(size=(136,13));x[:40]+=2
  with tempfile.TemporaryDirectory() as d:
   tree=compute_single_linkage(x.astype(np.float64),Path(d)/'D.tmp',min_samples=10,block=43)
   a,_=tree_to_labels(tree,30,cluster_selection_method='eom',allow_single_cluster=False,cluster_selection_epsilon=0,max_cluster_size=None)
   b=HDBSCAN(min_samples=10,min_cluster_size=30,metric='euclidean').fit_predict(x)
   self.assertEqual(adjusted_rand_score(a,b),1.0)
 def test_empty_or_corrupted_nonfinite_not_accepted(self):
  with tempfile.TemporaryDirectory() as d:
   x=np.full((30,7),np.nan)
   with self.assertRaises(AssertionError):compute_single_linkage(x,Path(d)/'D.tmp',min_samples=5)

if __name__=='__main__':unittest.main()
