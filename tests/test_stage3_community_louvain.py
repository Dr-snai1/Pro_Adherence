"""Source-free synthetic tests for Stage3 Louvain research diagnostics."""
import importlib.util
from pathlib import Path
import struct
import unittest
import networkx as nx

SOURCE=Path(__file__).resolve().parents[1]/'scripts'/'stage3_community_louvain.py'
if not SOURCE.exists():
    SOURCE=Path(__file__).with_name('stage3_community_louvain.py')
spec=importlib.util.spec_from_file_location('stage3_community_louvain',SOURCE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def uleb(x):
    b=bytearray()
    while x>=128:
        b.append((x&127)|128)
        x>>=7
    b.append(x)
    return bytes(b)


class LouvainTests(unittest.TestCase):
    def test_frozen_pac1_decode_sorted_weights(self):
        keys=[1,17,19]
        weights=[1,4,2]
        body=bytearray();prev=-1
        for key,w in zip(keys,weights):
            body+=uleb(key-prev)+uleb(w);prev=key
        packed=b'PAC1'+struct.pack('<III',m.N,3,7)+body
        rows,total=m.decode_pac1(packed)
        self.assertEqual(total,7)
        self.assertEqual(rows,[(0,1,1),(0,17,4),(0,19,2)])

    def test_reject_repeated_or_decreasing_pac1_key(self):
        raw=b'PAC1'+struct.pack('<III',m.N,2,2)+uleb(2)+uleb(1)+uleb(0)+uleb(1)
        with self.assertRaisesRegex(ValueError,'noncanonical'):
            m.decode_pac1(raw)

    def test_reject_bad_pac1_weight_or_header(self):
        p=b'PAC1'+struct.pack('<III',m.N,1,0)+uleb(2)+uleb(0)
        with self.assertRaises(ValueError): m.decode_pac1(p)
        with self.assertRaises(ValueError): m.decode_pac1(b'NOTPAC1')

    def test_community_cover_and_structural_missing(self):
        partitions=[{0,1},{3,4}]
        membership,sizes=m.canonical_membership(partitions,{0,1,3,4},n=6)
        self.assertEqual(membership,[0,0,-1,1,1,-1])
        self.assertEqual(sizes,[2,2])
        with self.assertRaises(ValueError):
            m.canonical_membership([{0,1},{1,3}],{0,1,3},n=4)
        with self.assertRaises(ValueError):
            m.canonical_membership([{0,1}],{0,1,2},n=4)

    def test_modularity_independent_formula_and_resolution(self):
        edges=[(0,1,3),(0,2,1),(2,3,4),(3,4,1)]
        G=m.make_graph(edges,n=6)
        groups=[{0,1},{2,3,4}]
        membership,_=m.canonical_membership(groups,G.nodes(),n=6)
        for gamma in [0.5,1.0,1.75]:
            independent,total,inside=m.independent_modularity(edges,membership,gamma,n=6)
            standard=nx.community.modularity(G,groups,weight='weight',resolution=gamma)
            self.assertAlmostEqual(independent,standard,places=12)
            self.assertEqual(total,9)
            self.assertEqual(inside,8)

    def test_louvain_small_graph_reproducibility(self):
        edges=[(0,1,3),(0,2,2),(1,2,3),(3,4,3),(3,5,2),(4,5,3),(2,3,1)]
        G=m.make_graph(edges,n=8)
        result1,stats1=m.run_louvain(G,edges,1.,42,n=8)
        result2,stats2=m.run_louvain(G,edges,1.,42,n=8)
        self.assertEqual(result1,result2)
        self.assertEqual(result1[6:],[None,None] if False else [-1,-1])
        self.assertEqual(stats1['active_nodes'],6)
        self.assertEqual(stats1['structural_missing_nodes'],2)
        self.assertAlmostEqual(stats1['modularity'],stats2['modularity'])
        self.assertAlmostEqual(stats1['independent_modularity'],stats1['modularity'])

    def test_partition_stability_label_invariance(self):
        arrays=[[0,0,1,1,2,2,-1],[8,8,7,7,6,6,-1]]
        s=m.sensitivity(arrays,range(6),runs=[(1.,42),(1.,43)])
        self.assertEqual(len(s),1)
        self.assertAlmostEqual(s[0]['adjusted_rand'],1.0)
        self.assertAlmostEqual(s[0]['normalized_mutual_information'],1.0)

if __name__=='__main__':unittest.main()
