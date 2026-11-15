"""Source-free tests for raw WoS/APA observation parsing and source-scoped weights."""
import gzip
import importlib.util
import io
import pathlib
import sqlite3
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "stage3_sourceaware_observations.py"
spec = importlib.util.spec_from_file_location("stage3_sourceaware", SCRIPT)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RawSourceObservationsTests(unittest.TestCase):
    def test_wos_tagged_authors_and_separate_keyword_fields(self):
        txt = ("FN Clarivate\nVR 1.0\nPT J\nAU Lee, A\n   Smith, B\n"
               "C1 Department of Medicine\nDE medication adherence; persistence;\n"
               "   initiation\nID PATIENT; TREATMENT\nUT WOS:000000000001\nER\nEF\n")
        items = list(m.wos_records(io.BytesIO(txt.encode())))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["AU"], ["Lee, A", "Smith, B"])
        self.assertEqual(items[0]["UT"], ["WOS:000000000001"])
        self.assertEqual(m.labels(items[0]["DE"], split_semicolon=True)[0],
                         ["initiation", "medication adherence", "persistence"])
        self.assertEqual(m.labels(items[0]["ID"], split_semicolon=True)[0],
                         ["PATIENT", "TREATMENT"])

    def test_ris_apa_multitag_kw_and_author(self):
        ris = ("TY  - JOUR\nAN  - 0000-0000-001\nAU  - Lee, A\nAU  - Smith, B\n"
               "KW  - medication adherence\nKW  - adherence measures\n"
               "TI  - Synthetic title\nER  - \n\n")
        rows = list(m.apa_records(io.BytesIO(ris.encode())))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["AN"], ["0000-0000-001"])
        self.assertEqual(rows[0]["AU"], ["Lee, A", "Smith, B"])
        self.assertEqual(rows[0]["KW"], ["medication adherence", "adherence measures"])

    def test_scoped_names_are_not_people_and_exact_pair_weights(self):
        stats = {k: __import__("collections").Counter() for k in (
            "duplicate_labels_within_record", "observed_raw_mentions",
            "unique_phrase_occurrences", "eligible_records_with_phrases",
            "possible_pair_events")}
        with sqlite3.connect(":memory:") as db:
            m.setup_db(db)
            m.observe(db, "author_names", "pubmed", ["Lee J", "Smith A"], stats)
            m.observe(db, "author_names", "pubmed", ["Lee J", "Smith A"], stats)
            m.observe(db, "author_names", "woscc", ["Lee J", "Smith A"], stats)
            m.observe(db, "author_names", "pubmed", ["Lee j", "Smith A"], stats)
            self.assertEqual(db.execute(
                "SELECT COUNT(*),SUM(weight) FROM edges WHERE source='pubmed'"
            ).fetchone(), (2, 3))
            self.assertEqual(db.execute(
                "SELECT COUNT(*),SUM(weight) FROM edges WHERE source='woscc'"
            ).fetchone(), (1, 1))
            self.assertEqual(stats["possible_pair_events"]["author_names|pubmed"], 3)
            self.assertEqual(stats["possible_pair_events"]["author_names|woscc"], 1)

    def test_unicode_nfc_and_keyword_layer_separation(self):
        self.assertEqual(m.labels(["  Cafe\u0301 ", "Café"])[0], ["Café"])
        self.assertEqual(m.labels(["a;b", " b;c "], split_semicolon=True)[0],
                         ["a", "b", "c"])
        stats = {k: __import__("collections").Counter() for k in (
            "duplicate_labels_within_record", "observed_raw_mentions",
            "unique_phrase_occurrences", "eligible_records_with_phrases",
            "possible_pair_events")}
        with sqlite3.connect(":memory:") as db:
            m.setup_db(db)
            m.observe(db, "wos_DE", "woscc", ["a;b"], stats)
            m.observe(db, "wos_ID", "woscc", ["a;b"], stats)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM edges").fetchone()[0], 2)

    def test_gzip_stream_determinism_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = pathlib.Path(tmp) / "a.gz", pathlib.Path(tmp) / "b.gz"
            first = m.write_gz(a, iter([["author_names", "woscc", "a", "b", 2]]))
            second = m.write_gz(b, iter([["author_names", "woscc", "a", "b", 2]]))
            self.assertEqual(first["sha256"], second["sha256"])
            with gzip.open(a, "rt") as f:
                self.assertIn("author_names", f.read())
            with self.assertRaises(FileExistsError):
                m.write_gz(a, iter([]))


if __name__ == "__main__":
    unittest.main()
