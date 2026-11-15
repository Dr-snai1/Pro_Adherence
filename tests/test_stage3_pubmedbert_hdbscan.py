#!/usr/bin/env python3
"""Source-free exact-HDBSCAN tree-extraction and sample-design regression tests."""
import sys,unittest
from pathlib import Path
import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.metrics import adjusted_rand_score
sys.path.insert(0,str(Path(__file__).resolve().parents[0]))
from stage3_pubmedbert_hdbscan_pilot import extract_thresholds

class TestHdbscanResearchPilot(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  rng=np.random.default_rng(511)
  a=rng.normal(loc=-2,scale=0.25,size=(120,32))
  b=rng.normal(loc=2,scale=0.25,size=(120,32))
  noise=rng.normal(loc=0,scale=4,size=(40,32))
  cls.X=np.vstack([a,b,noise]).astype(np.float64)
  cls.X/=np.linalg.norm(cls.X,axis=1,keepdims=True)

 def test_grid_exact_agrees_independent_fits(self):
  values,_=extract_thresholds(self.X,10,thresholds=(15,30,60),n_jobs=1)
  for threshold in (15,30,60):
   lab=HDBSCAN(min_cluster_size=threshold,min_samples=10,metric='euclidean',algorithm='auto',n_jobs=1,copy=True).fit_predict(self.X)
   self.assertEqual(1.,adjusted_rand_score(lab,values[threshold]['labels']))
   self.assertEqual(int((lab<0).sum()),values[threshold]['metrics']['noise'])

 def test_threshold_assignment_partition(self):
  vals,_=extract_thresholds(self.X,5,thresholds=(10,30,50),n_jobs=1)
  for v in vals.values():
   m=v['metrics'];self.assertEqual(len(self.X),m['assigned']+m['noise'])
   self.assertTrue(np.all((v['probabilities']>=0)&(v['probabilities']<=1)))
   self.assertEqual(m['clusters'],len(set(v['labels'][v['labels']>=0])))

 def test_seed_reproducible_strict_nested_samples(self):
  rs=[]
  for _ in range(2):
   rng=np.random.default_rng(20261031)
   idx=np.sort(rng.choice(57204,size=12000,replace=False))
   nest=np.sort(rng.choice(idx,size=6000,replace=False))
   self.assertTrue(np.array_equal(idx[np.searchsorted(idx,nest)],nest));rs.append((idx,nest))
  self.assertTrue(np.array_equal(rs[0][0],rs[1][0]));self.assertTrue(np.array_equal(rs[0][1],rs[1][1]))

 def test_duplicate_vectors_are_not_nonfinite(self):
  x=np.vstack([self.X,np.tile(self.X[0],(12,1))])
  vals,_=extract_thresholds(x,10,thresholds=(20,30,50),n_jobs=1)
  for v in vals.values():self.assertTrue(np.isfinite(v['probabilities']).all())

 def test_view_comparison_same_point_order(self):
  idx=np.arange(0,120);a=self.X[idx];b=self.X[idx].copy()
  l1,_=extract_thresholds(a,5,thresholds=(12,20),n_jobs=1)
  l2,_=extract_thresholds(b,5,thresholds=(12,20),n_jobs=1)
  for t in (12,20):self.assertEqual(1.,adjusted_rand_score(l1[t]['labels'],l2[t]['labels']))

if __name__=='__main__':unittest.main()
