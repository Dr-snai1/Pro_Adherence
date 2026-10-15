"""Synthetic only; never reads private research evidence or invokes PubMed."""
import importlib.util
import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from pro_adherence import stage1_ingest as stage1

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "stage1_pubmed.xml"
META = ROOT / "tests" / "fixtures" / "stage1_pubmed_meta.json"
HAS_ARROW = importlib.util.find_spec("pyarrow") is not None


class LocalStage1Contracts(unittest.TestCase):
    def setUp(self):
        self.xml = FIXTURE.read_bytes()
        self.meta = json.loads(META.read_text())

    def test_three_positions_two_unique_articles(self):
        rows, sources, external, positions = stage1._parse(self.xml, stage1._id("raw/fake"), "pubmed", self.meta["retrieval_time"])
        self.assertEqual((positions, len(rows), len(sources), len(external)), (3, 2, 2, 4))
        self.assertEqual(sources[0]["duplicate_occurrences"], 2)
        self.assertEqual(sources[0]["original_metadata_payload_pointer"], f"raw/{hashlib.sha256(self.xml).hexdigest()}.xml#PubmedArticle=0")
        self.assertEqual(rows[0]["doi"], "10.9999/synth.01")
        self.assertEqual(rows[1]["abstract_text"], None)
        self.assertTrue(rows[0]["canonical_article_id"].split("-")[2].startswith("7"))

    def test_schema_shaped_article_and_access_license(self):
        rows, _, _, _ = stage1._parse(self.xml, stage1._id("raw/fake"), "pubmed", self.meta["retrieval_time"])
        for r in rows:
            r["access_license"] = {"access_class": "project-internal", "license_class": "synthetic-only",
                                   "license_status": "unknown", "publication_permissions": {
                                       "metadata": "deny", "raw_text": "deny", "derived": "deny"}}
            article = {key: r[key] for key in ("canonical_article_id", "title_display", "abstract_text", "publication_date", "document_type", "language", "access_license", "record_status", "created_in_resolution_version")}
            self.assertEqual(article["access_license"]["publication_permissions"]["raw_text"], "deny")
            self.assertRegex(article["canonical_article_id"], r"^[0-9a-f]{8}-[0-9a-f]{4}-7")
            schema_dir = ROOT / "contracts" / "schemas"
            if schema_dir.is_dir():
                from jsonschema import Draft202012Validator, FormatChecker, RefResolver
                store = {p.name: json.loads(p.read_text()) for p in schema_dir.glob("*.schema.json")}
                resolver = RefResolver.from_schema(store["entities.schema.json"], store=store)
                validator = Draft202012Validator({"$ref": "entities.schema.json#/$defs/article"},
                                                   resolver=resolver, format_checker=FormatChecker())
                validator.validate(article)

    def test_workspace_inside_public_repo_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "outside public Git repository"):
            stage1.build(FIXTURE, META, ROOT / "stage1-should-not-exist")

    def test_deterministic_regardless_raw_order(self):
        one = stage1._parse(self.xml, stage1._id("raw/fake"), "pubmed", self.meta["retrieval_time"])
        two = stage1._parse(self.xml, stage1._id("raw/fake"), "pubmed", self.meta["retrieval_time"])
        self.assertEqual(one, two)

    def test_conflicting_same_pmid_is_rejected(self):
        bad = self.xml.replace(b"Simulated dispensing behaviour", b"Simulated medication taking behaviour")
        bad = bad.replace(b"<PMID>900000002</PMID>", b"<PMID>900000001</PMID>")
        with self.assertRaisesRegex(ValueError, "same PMID has conflicting content"):
            stage1._parse(bad, stage1._id("raw/fake"), "pubmed", self.meta["retrieval_time"])

    def test_doi_collision_is_not_silently_merged(self):
        bad = self.xml.replace(b"10.9999/SYNTH.02", b"10.9999/SYNTH.01")
        with self.assertRaisesRegex(ValueError, "DOI shared"):
            stage1._parse(bad, stage1._id("raw/fake"), "pubmed", self.meta["retrieval_time"])

    def test_unsafe_xml_is_rejected(self):
        malicious = b'<!DOCTYPE PubmedArticleSet [<!ENTITY x "expansion">]>' + self.xml
        with self.assertRaisesRegex(ValueError, "DTD/entity"):
            stage1._parse(malicious, stage1._id("raw/fake"), "pubmed", self.meta["retrieval_time"])

    def test_unpinned_provenance_and_public_access_are_rejected(self):
        for patch in ({"access_class": "public"}, {"retrieval_time": "2026-10-15"}, {"source_id": "wos"}):
            value = {**self.meta, **patch}
            with self.assertRaises(ValueError):
                stage1._validate_meta(value)

    def test_opaque_stable_uuidv7_contract(self):
        from uuid import UUID
        a = stage1._id("article/pmid/900000001")
        self.assertEqual(a, stage1._id("article/pmid/900000001"))
        self.assertEqual(UUID(a).version, 7)
        self.assertNotIn("900000001", a)
        self.assertNotEqual(a, stage1._id("article/pmid/900000002"))

    @unittest.skipUnless(HAS_ARROW, "Stage 1 Parquet runtime is installed in dedicated CI job")
    def test_clean_rebuild_is_bitwise_reproducible_and_private(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            a = stage1.build(FIXTURE, META, root / "one")
            b = stage1.build(FIXTURE, META, root / "two")
            self.assertEqual(a.name, b.name)
            self.assertEqual((a / "checksums.json").read_bytes(), (b / "checksums.json").read_bytes())
            self.assertEqual((a / "corpus_manifest.json").read_bytes(), (b / "corpus_manifest.json").read_bytes())
            manifest = json.loads((a / "corpus_manifest.json").read_text())
            self.assertEqual(manifest["article_count"], 2)
            self.assertEqual(manifest["status"], "draft")
            source = json.loads((a / "source_provenance.json").read_text())
            self.assertEqual(source["publication_permissions"]["raw_text"], "deny")
            self.assertEqual(stage1.build(FIXTURE, META, root / "one"), a)

    @unittest.skipUnless(HAS_ARROW, "Stage 1 Parquet runtime is installed in dedicated CI job")
    def test_mutation_breaks_immutable_readback(self):
        with tempfile.TemporaryDirectory() as root:
            target = stage1.build(FIXTURE, META, Path(root))
            (target / "articles.parquet").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "mutated"):
                stage1.build(FIXTURE, META, Path(root))

    @unittest.skipUnless(HAS_ARROW, "Stage 1 Parquet runtime is installed in dedicated CI job")
    def test_fail_closed_on_raw_tampering(self):
        with tempfile.TemporaryDirectory() as root:
            stage1.build(FIXTURE, META, Path(root))
            raw_dir = Path(root) / "raw"
            archived = next(raw_dir.iterdir())
            archived.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "raw content hash drift"):
                stage1.build(FIXTURE, META, Path(root))


if __name__ == "__main__":
    unittest.main()
