"""Synthetic offline export tests; never access private Stage2 corpus."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from pro_adherence.stage3_contracts import Stage3ContractError
from scripts.stage3_graph_snapshot import materialize_private_graph


def _synthetic_graph():
    nodes = [
        {"article_id": "article:A", "eligible": True,
         "reference_coverage": ["exposed"], "has_observed_resolved_edge": True,
         "isolate_reason": None},
        {"article_id": "article:B", "eligible": False,
         "reference_coverage": ["unknown"], "has_observed_resolved_edge": False,
         "isolate_reason": "excluded_by_policy"},
        {"article_id": "article:C", "eligible": True,
         "reference_coverage": ["exposed"], "has_observed_resolved_edge": True,
         "isolate_reason": None},
    ]
    edge = {"source_article_id": "article:C", "target_article_id": "article:A",
            "weight": 1, "observation_count": 2, "evidence_pointers": [
                {"source_record_id": "synthetic:1", "raw_reference_ordinal": 1,
                 "export_sha256": "a" * 64, "record_ordinal": 1},
                {"source_record_id": "synthetic:1", "raw_reference_ordinal": 2,
                 "export_sha256": "a" * 64, "record_ordinal": 1}]}
    d = {"article_count": 3, "eligible_article_count": 3,
         "citation_status_counts": {"exact_doi": 2, "ambiguous_doi": 1, "unresolved": 1},
         "edge_observation_count": 2, "edge_count": 1,
         "nodes": deepcopy(nodes), "edges": [edge]}
    walk = deepcopy(edge)
    walk["source_article_id"], walk["target_article_id"] = "article:A", "article:C"
    t = {"article_count": 3, "eligible_article_count": 2,
         "citation_status_counts": d["citation_status_counts"],
         "edge_observation_count": 2, "edge_count": 1,
         "excluded_edge_observations": {},
         "nodes": deepcopy(nodes), "edges": [walk]}
    return {"directed_citation_graph": d, "node2vec_training_graph": t}


class Stage3GraphSnapshotTests(unittest.TestCase):
    def test_byte_determinism_and_private_roundtrip(self):
        graph = _synthetic_graph()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            m1 = materialize_private_graph(graph, p / "a", expected_canonical=3,
                     expected_eligible=2, expected_citations=4, expected_exact_doi=2)
            m2 = materialize_private_graph(graph, p / "b", expected_canonical=3,
                     expected_eligible=2, expected_citations=4, expected_exact_doi=2)
            self.assertEqual(m1, m2)
            self.assertFalse(m1["publication_authorized"])
            self.assertFalse(m1["training_executed"])
            self.assertEqual(m1["graph_snapshot"]["eligible_node_count"], 2)
            with gzip.open(p / "a" / m1["outputs"]["node_mapping"]["name"], "rt") as f:
                rows = [json.loads(line) for line in f]
            self.assertEqual([r["article_id"] for r in rows], ["article:A", "article:C"])
            self.assertEqual([r["node_index"] for r in rows], [0, 1])
            with self.assertRaisesRegex(Stage3ContractError, "destination must be empty"):
                materialize_private_graph(graph, p / "a", expected_canonical=3,
                     expected_eligible=2, expected_citations=4, expected_exact_doi=2)

    def test_rejects_policy_violation_and_missing_citation_count(self):
        graph = _synthetic_graph()
        with tempfile.TemporaryDirectory() as tmp:
            g = deepcopy(graph)
            g["node2vec_training_graph"]["edges"][0]["weight"] = 2
            with self.assertRaisesRegex(Stage3ContractError, "invalid binary undirected"):
                materialize_private_graph(g, Path(tmp) / "one", expected_canonical=3,
                    expected_eligible=2, expected_citations=4, expected_exact_doi=2)
            g = deepcopy(graph)
            g["node2vec_training_graph"]["edges"][0]["target_article_id"] = "article:B"
            with self.assertRaisesRegex(Stage3ContractError, "invalid binary undirected"):
                materialize_private_graph(g, Path(tmp) / "two", expected_canonical=3,
                    expected_eligible=2, expected_citations=4, expected_exact_doi=2)
            with self.assertRaisesRegex(Stage3ContractError, "citation census mismatch"):
                materialize_private_graph(graph, Path(tmp) / "three", expected_canonical=3,
                    expected_eligible=2, expected_citations=3, expected_exact_doi=2)


if __name__ == "__main__":
    unittest.main()
