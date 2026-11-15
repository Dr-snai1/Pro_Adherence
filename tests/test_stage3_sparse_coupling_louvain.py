import unittest
import numpy as np
import scipy.sparse as sp
import networkx as nx
from stage3_sparse_coupling_louvain import local_sweep,modularity_raw,run_one,decode_bytes

class TestSparseLouvain(unittest.TestCase):
    def matrix(self,edges,n):
        r=np.array([x for u,v,w in edges for x in [u,v]],dtype=np.int32)
        c=np.array([x for u,v,w in edges for x in [v,u]],dtype=np.int32)
        w=np.array([z for u,v,z in edges for _ in [0,1]],dtype=np.int32)
        return sp.coo_matrix((w,(r,c)),shape=(n,n)).tocsr()
    def test_modularity_networkx_two_partition(self):
        edges=[(0,1,2),(0,2,3),(1,2,4),(3,4,2),(3,5,3),(4,5,5),(2,3,1)]
        a=self.matrix(edges,8)
        labels=np.array([0,0,0,1,1,1,2,3],dtype=np.int32)
        # isolates contribute nothing to modularity
        G=nx.Graph();G.add_weighted_edges_from(edges)
        for gamma in [0.75,1.0,1.25]:
            observed,*_=modularity_raw(a.indptr,a.indices,a.data,labels,gamma)
            expected=nx.community.modularity(G,[{0,1,2},{3,4,5}],resolution=gamma,weight='weight')
            self.assertAlmostEqual(observed,expected,places=12)
    def test_clusters_isolates_and_modularity(self):
        edges=[(0,1,4),(0,2,4),(1,2,4),(3,4,4),(3,5,4),(4,5,4),(2,3,1)]
        a=self.matrix(edges,8)
        active=np.asarray(a.sum(axis=1)).ravel()>0
        lab,info=run_one(a,active,1.0,20261031)
        self.assertTrue(np.array_equal(lab[6:],[-1,-1]));self.assertEqual(info['active_nodes'],6)
        self.assertEqual(info['communities'],2)
        self.assertAlmostEqual(info['modularity'],info['independent_modularity'],places=12)
        self.assertGreater(info['modularity'],0)
    def test_empty_and_disconnected(self):
        a=self.matrix([(0,1,2),(2,3,1)],6)
        active=np.asarray(a.sum(axis=1)).ravel()>0
        lab,info=run_one(a,active,1.0,20261031)
        self.assertEqual(info['communities'],2);self.assertTrue(np.array_equal(lab[4:],[-1,-1]))
    def test_reproducibility(self):
        a=self.matrix([(0,1,3),(0,2,4),(1,2,3),(3,4,4),(4,5,4),(3,5,3),(2,3,1)],6)
        active=np.ones(6,dtype=bool)
        x,info=run_one(a,active,0.75,20261031)
        y,info2=run_one(a,active,0.75,20261031)
        self.assertTrue(np.array_equal(x,y));self.assertEqual(info['modularity'],info2['modularity'])
    def test_sweep_monotonic_and_weight_conservation(self):
        a=self.matrix([(0,1,2),(1,2,3),(2,3,4)],5)
        labels=np.arange(5,dtype=np.int32);degree=np.asarray(a.sum(axis=1)).ravel().astype(float);tot=degree.copy()
        local_sweep(a.indptr,a.indices,a.data,labels,tot,degree,float(degree.sum()),1.0,np.arange(5,dtype=np.int32))
        self.assertAlmostEqual(tot.sum(),degree.sum());self.assertTrue(np.all(tot>=0))
    def test_decode_small_header(self):
        # header for 5 nodes, pairs=2, incidence=4; keys 1 and 8
        import struct
        blob=b'PAC1'+struct.pack('<III',5,2,4)+bytes([2,2,7,2])
        a,b,c,total=decode_bytes(np.frombuffer(blob,dtype=np.uint8),5,2)
        self.assertEqual(list(zip(a,b,c)),[(0,1,2),(1,3,2)])
        self.assertEqual(total,4)

if __name__=='__main__':unittest.main(verbosity=2)
