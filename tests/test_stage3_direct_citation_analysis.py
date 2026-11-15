"""Source-free Stage3 direct-citation tests. Never load private research data."""
from __future__ import annotations
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / 'scripts' / 'stage3_direct_citation_analysis.py'
spec = importlib.util.spec_from_file_location('direct_citation', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def gzip_member(rows):
    import io
    buf = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=buf, mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, sort_keys=True) + '\n').encode())
    return buf.getvalue()


def sample_zip(path, *, mismatch=False):
    node_ids = ['article:A', 'article:B', 'article:C', 'article:D']
    mapping = [{'node_index': i, 'article_id': article} for i, article in enumerate(node_ids)]
    # A->B, B->C, C->B, and C->D; one self and one out-of-cohort edge.
    edges = [('article:A', 'article:B', 2 if not mismatch else 3),
             ('article:B', 'article:C', 1), ('article:C', 'article:B', 1),
             ('article:C', 'article:D', 1), ('article:A', 'article:A', 1),
             ('article:X', 'article:A', 1)]
    directed = [{'source_article_id': s, 'target_article_id': t, 'weight': 1,
                 'observation_count': count} for s, t, count in edges]
    evidence = [{'source_article_id': s, 'target_article_id': t,
                 'source_record_id': ('pubmed:1' if k == 0 else 'woscc:1')}
                for s, t, count in edges for k in range(2 if s == 'article:A' and t == 'article:B' else 1)]
    contents = {'node2vec_node_mapping.private.jsonl.gz': gzip_member(mapping),
                'directed_edges.private.jsonl.gz': gzip_member(directed),
                'directed_citation_evidence.private.jsonl.gz': gzip_member(evidence)}
    manifest = {'eligible_count': 4, 'outputs': {name: {'sha256': hashlib.sha256(blob).hexdigest()}
                                                 for name, blob in contents.items()}}
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, blob in contents.items():
            z.writestr(name, blob)
        z.writestr('node2vec_graph_manifest.private.json', json.dumps(manifest))


class DirectCitationTests(unittest.TestCase):
    def test_directed_semantics_and_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'synthetic.zip'
            sample_zip(path)
            ids, adj, rev, lineage = m.ingest_graph(path, verify_frozen=False)
            self.assertEqual(len(ids), 4)
            self.assertEqual(sum(map(len, adj)), 4)
            self.assertEqual(lineage['counts']['excluded_edges'], 1)
            self.assertEqual(lineage['counts']['self_edges'], 1)
            self.assertEqual(lineage['counts']['evidence_all'], 7)
            self.assertEqual(lineage['eligible_edge_source_sets'],
                             {'pubmed_only': 3, 'woscc_only': 0, 'both_sources': 1})
            self.assertEqual(list(map(len, rev)), [0, 2, 1, 1])

    def test_wcc_and_scc_keep_direction(self):
        adj = [[1], [2], [1, 3], [], [], [6], []]
        rev = [[], [0, 2], [1], [2], [], [], [5]]
        wi, ws = m.weak_components(adj, rev)
        si, ss = m.strong_components(adj, rev)
        self.assertEqual(ws, [4, 2, 1])
        self.assertEqual(ss, [2, 1, 1, 1, 1, 1])
        self.assertEqual(wi[0], wi[3])
        self.assertNotEqual(si[0], si[3])
        self.assertEqual(si[1], si[2])

    def test_rank_preserves_indegree_outdegree_orientation(self):
        ids = ['A', 'B', 'C']
        adj = [[1, 2], [], [1]]
        rev = [[], [0, 2], [0]]
        summary, ranks, metrics = m.summarize_nodes(ids, adj, rev, {})
        self.assertEqual(summary['in_degree_sum'], 3)
        self.assertEqual(summary['isolated_nodes'], 0)
        self.assertEqual(ranks['by_indegree_top100'][0]['article_id'], 'B')
        self.assertEqual(ranks['by_outdegree_top100'][0]['article_id'], 'A')
        self.assertEqual(len(list(metrics)), 3)

    def test_pagerank_stationary_and_dangling(self):
        result, info = m.pagerank([[1], [0]])
        self.assertAlmostEqual(result[0], 0.5, places=12)
        self.assertAlmostEqual(result[1], 0.5, places=12)
        self.assertTrue(info['converged'])
        result, info = m.pagerank([[1], [], []])
        self.assertAlmostEqual(sum(result), 1, places=12)
        self.assertGreater(result[1], result[0])
        self.assertGreater(result[1], result[2])

    def test_hash_and_evidence_validation(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'synthetic.zip'
            sample_zip(path, mismatch=True)
            with self.assertRaisesRegex(ValueError, 'observation_count'):
                m.ingest_graph(path, verify_frozen=False)
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                m.ingest_graph(path, verify_frozen=True)

    def test_output_is_deterministic_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)/'metrics.gz'
            metrics = [{'node_index': i, 'in_degree': 1, 'out_degree': 1}
                       for i in range(3)]
            r = m.save_node_gzip(out, iter(metrics))
            self.assertEqual(r['rows'], 3)
            with self.assertRaises(FileExistsError):
                m.save_node_gzip(out, iter(metrics))
            out2 = Path(td)/'metrics2.gz'
            r2 = m.save_node_gzip(out2, iter(metrics))
            self.assertEqual(r['sha256'], r2['sha256'])


if __name__ == '__main__':
    unittest.main()
