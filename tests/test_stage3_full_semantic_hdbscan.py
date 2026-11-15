"""Source-free synthetic tests for exact full HDBSCAN archival runner."""
import os,gzip,json,hashlib,tempfile,unittest
from pathlib import Path
import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.cluster._hdbscan.hdbscan import tree_to_labels
from stage3_full_semantic_hdbscan import sha

class TestFullSemanticHDBSCAN(unittest.TestCase):
 def test_exact_threshold_reuse(self):
  rng=np.random.default_rng(4202)
  x=np.vstack([rng.normal(loc=i*8,scale=.5,size=(70,8)) for i in range(3)])
  from scipy.spatial.distance import cdist
  x=x/np.linalg.norm(x,axis=1)[:,None]
  model=HDBSCAN(min_cluster_size=15,min_samples=5,cluster_selection_method='eom',metric='euclidean')
  model.fit(x)
  for k in (15,25,45):
   lab,pr=tree_to_labels(model._single_linkage_tree_,k,cluster_selection_method='eom',allow_single_cluster=False,cluster_selection_epsilon=0,max_cluster_size=None)
   separate=HDBSCAN(min_cluster_size=k,min_samples=5,cluster_selection_method='eom',metric='euclidean').fit(x)
   from sklearn.metrics import adjusted_rand_score
   self.assertAlmostEqual(adjusted_rand_score(lab,separate.labels_),1.0)
   self.assertTrue(np.allclose(np.sort(pr),np.sort(separate.probabilities_),atol=1e-9))
 def test_determinism(self):
  rng=np.random.default_rng(4242);x=rng.normal(size=(135,10))
  x=x/np.linalg.norm(x,axis=1)[:,None]
  a=HDBSCAN(min_cluster_size=12,min_samples=3,metric='euclidean').fit(x)
  b=HDBSCAN(min_cluster_size=12,min_samples=3,metric='euclidean').fit(x)
  np.testing.assert_array_equal(a.labels_,b.labels_)
 def test_missing_vector_separation(self):
  rec={'article_id':'article:test','node_index':0,'labels':{'30':None},'noise':{'30':True},'membership_strength':{'30':0.0}}
  self.assertTrue(rec['noise']['30'])
  self.assertIsNone(rec['labels']['30'])
 def test_sha_repeat(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'tiny.txt';f.write_bytes(b'private-data-should-not-leak')
   self.assertEqual(sha(f),hashlib.sha256(f.read_bytes()).hexdigest())
 def test_eligible_matrix_shape(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.npy';np.save(p,np.zeros((6,768),dtype=np.float32))
   self.assertEqual(np.load(p,mmap_mode='r').shape,(6,768))

if __name__=='__main__':unittest.main()
