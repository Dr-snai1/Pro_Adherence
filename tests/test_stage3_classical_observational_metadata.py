"""Synthetic only; never loads private Stage2 observations or author strings."""
from __future__ import annotations
import gzip
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "stage3_classical_observational_metadata.py"
spec = importlib.util.spec_from_file_location("stage3_observational", SOURCE)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MetadataObservationTests(unittest.TestCase):
    def test_labels_preserve_orthography_and_unicode(self):
        self.assertEqual(m.nfc_label("  Cafe\u0301  "), "Café")
        self.assertNotEqual(m.nfc_label("SMITH J"), m.nfc_label("Smith J"))
        self.assertEqual(m.phrase_labels([" a ; b ", "b", " C "],
                                         split_semicolon=True), ["C", "a", "b"])
        self.assertEqual(m.phrase_labels([" a ; b "],
                                         split_semicolon=False), ["a ; b"])
        with self.assertRaises(ValueError):
            m.phrase_labels("not a list", split_semicolon=True)
        with self.assertRaises(ValueError):
            m.nfc_label(None)

    def test_source_scoped_nodes_not_mistaken_for_person_identity(self):
        self.assertNotEqual(m.node_id("pubmed", "Lee J"), m.node_id("woscc", "Lee J"))
        self.assertNotEqual(m.node_id("pubmed", "Lee J"), m.node_id("pubmed", "Lee JR"))

    def test_exact_shared_author_string_pair_multiplicity(self):
        with sqlite3.connect(":memory:") as db:
            m.init_db(db)
            self.assertEqual(m.observe(db, "author_names_not_persons", "woscc",
                                       ["Alice", "Bob", "Zoe"]), (3, 3))
            self.assertEqual(m.observe(db, "author_names_not_persons", "woscc",
                                       ["Alice", "Bob"]), (2, 1))
            self.assertEqual(m.observe(db, "author_names_not_persons", "pubmed",
                                       ["Alice", "Bob"]), (2, 1))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM edges").fetchone()[0], 4)
            rows = list(db.execute("SELECT source,weight FROM edges ORDER BY source,weight"))
            self.assertEqual(rows, [("pubmed", 1), ("woscc", 1),
                                    ("woscc", 1), ("woscc", 2)])
            with self.assertRaises(ValueError):
                m.observe(db, "author_names_not_persons", "woscc",
                          ["Alice", "Alice"])

    def test_keyword_phrase_network_and_source_separation(self):
        with sqlite3.connect(":memory:") as db:
            m.init_db(db)
            labels = m.phrase_labels(["treatment adherence; persistence",
                                      "persistence; compliance"], split_semicolon=True)
            self.assertEqual(labels, ["compliance", "persistence",
                                      "treatment adherence"])
            m.observe(db, "raw_keyword_phrases", "woscc", labels)
            m.observe(db, "raw_keyword_phrases", "woscc", labels[:2])
            self.assertEqual(db.execute(
                "SELECT COUNT(*),SUM(weight) FROM edges WHERE layer='raw_keyword_phrases'"
            ).fetchone(), (3, 4))

    def test_deterministic_gzip_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder, sqlite3.connect(":memory:") as db:
            m.init_db(db)
            m.observe(db, "author_names_not_persons", "woscc", ["A", "B"])
            sql = "SELECT layer,source,left_node,right_node,weight FROM edges ORDER BY 1,2,3,4"
            p1, p2 = Path(folder)/"one.gz", Path(folder)/"two.gz"
            a, b = m.save_table(db, sql, p1), m.save_table(db, sql, p2)
            self.assertEqual(a["sha256"], b["sha256"])
            self.assertEqual((a["rows"], a["weight_sum"]), (1, 1))
            with gzip.open(p1, "rt", encoding="utf-8") as f:
                self.assertEqual(len(f.readlines()), 1)
            with self.assertRaises(FileExistsError):
                m.save_table(db, sql, p1)

    def test_reject_incomplete_source_census(self):
        with sqlite3.connect(":memory:") as db:
            m.init_db(db)
            with self.assertRaisesRegex(ValueError, "source census mismatch"):
                m.process_source_records(db, [
                    {"source_record_id": "woscc:001", "source_id": "woscc",
                     "authors_raw": ["A", "B"], "keywords_raw": ["X;Y"]}],
                    {"woscc:001": "article:a"}, {"article:a"})


if __name__ == "__main__":
    unittest.main()
