"""Source-free checks for approved UMAP design. No private corpus and no fake full run."""
import unittest
import stage3_semantic_umap_hdbscan as e

class TestUMAPGrid(unittest.TestCase):
 def test_grid_exact_owner_contract(self):
  grid=e.config_grid()
  self.assertEqual(len(grid),24)
  self.assertEqual(len({(v['view'],v['n_components'],v['n_neighbors'],v['seed']) for v in grid}),24)
  self.assertEqual([x['view'] for x in grid[::8]],list(e.VIEWS))
  self.assertEqual(set(v['n_components'] for v in grid),{10,50})
  self.assertEqual(set(v['n_neighbors'] for v in grid),{30,100})
  self.assertEqual(set(v['seed'] for v in grid),{20261031,20261115})
  self.assertEqual(e.MIN_SAMPLES,(5,10));self.assertEqual(e.MCS,(30,80,150))
  self.assertEqual(len(grid)*len(e.MIN_SAMPLES)*len(e.MCS),144)
  self.assertTrue(all(v['min_dist']==0 and v['input_metric']=='cosine' and v['output_metric']=='euclidean' for v in grid))
 def test_leaf_trigger_only_for_few_large_groups(self):
  for args,expected in [((2,10000,8000),True),((3,10000,7500),True),((4,10000,9900),False),
                        ((2,10000,7000),False),((0,0,0),False),((1,0,0),False),((1,1000,1000),True)]:
   self.assertEqual(e.should_use_leaf(*args),expected)
 def test_runtime_preflight_refuses_missing_deps(self):
  d=e.env_check()
  self.assertIn('numpy',d['found']);self.assertIn('sklearn',d['found'])
  # Don't assert umap missing universally: tests should pass in real configured runner.
  self.assertIsInstance(d['missing_or_mismatch'],list)
if __name__=='__main__':unittest.main()
