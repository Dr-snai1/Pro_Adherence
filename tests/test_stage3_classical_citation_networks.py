"""Synthetic tests, containing no private corpus data.

Run from repository root in pinned Python 3.13 / numpy 2.3.5 runtime:
  python -m unittest discover -s tests -p 'test_stage3_classical_citation_networks.py'
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path
import importlib.util
import tempfile
import unittest

import numpy as np

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "stage3_classical_citation_networks.py"
spec = importlib.util.spec_from_file_location("citation_classics", SOURCE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def exact_oracle(neighborhoods, n):
    result = Counter()
    for group in neighborhoods:
        for a, b in combinations(sorted(set(group)), 2):
            result[a * n + b] += 1
    return dict(result)


class CitationClassicalTests(unittest.TestCase):
    def setUp(self):
        # Directed: A cites B,C; D cites B,C,E; F cites C.
        # Co-citation: BC=2, BE=1, CE=1.
        # Bibliographic coupling: AD=2, AF=1, DF=1.
        self.n = 6
        A, B, C, D, E, F = range(self.n)
        self.outgoing = [[B, C], [], [], [B, C, E], [], [C]]
        self.incoming = [[], [A, D], [A, D, F], [], [D], []]

    def test_exact_unthresholded_projections(self):
        for label, neighborhood, expected in [
            ("co_citation", self.outgoing, {1*6+2: 2, 1*6+4: 1, 2*6+4: 1}),
            ("bibliographic_coupling", self.incoming, {0*6+3: 2, 0*6+5: 1, 3*6+5: 1}),
        ]:
            with self.subTest(label=label):
                keys, weights, incidences = module.pair_projection(neighborhood, self.n)
                observed = dict(zip(map(int, keys), map(int, weights)))
                self.assertEqual(observed, expected)
                self.assertEqual(observed, exact_oracle(neighborhood, self.n))
                self.assertEqual(incidences, 4)
                self.assertEqual(len(keys), 3)
                self.assertEqual(sorted(map(int, weights)), [1, 1, 2])
                self.assertEqual(int(weights.sum()), incidences)

    def test_empty_pair_network(self):
        keys, weights, incidences = module.pair_projection([[], [1], [2], []], 4)
        self.assertEqual((len(keys), len(weights), incidences), (0, 0, 0))

    def test_duplicate_neighbor_rejected(self):
        with self.assertRaises(ValueError):
            module.pair_projection([[1, 1], [2], []], 3)

    def test_uint32_overflow_prevented(self):
        with self.assertRaises(ValueError):
            module.pair_projection([[]], 65_537)

    def test_gzip_asset_deterministic_and_replay(self):
        keys, weights, _ = module.pair_projection(self.outgoing, self.n)
        with tempfile.TemporaryDirectory() as d:
            f1 = Path(d) / "first.pairs.private.jsonl.gz"
            f2 = Path(d) / "second.pairs.private.jsonl.gz"
            a = module.emit_pairs(f1, keys, weights)
            b = module.emit_pairs(f2, keys, weights)
            self.assertEqual(a["sha256"], b["sha256"])
            self.assertEqual(a["rows"], 3)
            self.assertEqual(a["incidences"], 4)
            self.assertEqual(b["rows"], 3)
            with self.assertRaises(FileExistsError):
                module.emit_pairs(f1, keys, weights)


if __name__ == "__main__":
    unittest.main()
