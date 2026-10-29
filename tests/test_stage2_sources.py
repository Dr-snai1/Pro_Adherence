"""Focused synthetic unit tests for Stage 2 WoS tagged-text integration."""
import hashlib
import unittest

from pro_adherence.stage2_sources import (
    SourceFormatError,
    canonical_json,
    leave_one_source_out,
    normalize_doi,
    parse_wos_tagged_export,
    reconcile_sources,
)


SAMPLE = (
    "FN Clarivate Analytics Web of Science\n"
    "VR 1.0\n"
    "PT J\n"
    "AU Lee, A\n"
    "AU Chen, B\n"
    "TI Medication adherence\n"
    "   and implementation\n"
    "SO Example Journal\n"
    "DT Article\n"
    "PY 2024\n"
    "LA English\n"
    "DI 10.1234/Test-1\n"
    "PM 12345\n"
    "CR Zhang X, 2020, EXAMPLE, DOI 10.5678/reference\n"
    "UT WOS:000001\n"
    "ER\n"
    "PT J\n"
    "AU Patel, C\n"
    "TI Medication persistence\n"
    "DI 10.5678/reference\n"
    "UT WOS:000002\n"
    "ER\n"
    "EF\n"
).encode()


def synthetic(source_id, native_id, doi=None, pmid=None, refs=None):
    return {
        "source_id": source_id,
        "source_native_id": native_id,
        "source_record_id": f"{source_id}:{native_id}",
        "doi": doi,
        "pmid": pmid,
        "cited_references_raw": refs or [],
        "raw_export_sha256": "fixture",
        "raw_record_ordinal": 1,
    }


class Stage2SourcesTests(unittest.TestCase):
    def test_complete_wos_export_with_lineage_and_references(self):
        data = parse_wos_tagged_export(SAMPLE)
        self.assertEqual(data["record_count"], 2)
        self.assertEqual(data["raw_export_sha256"], hashlib.sha256(SAMPLE).hexdigest())
        a, b = data["records"]
        self.assertEqual(a["title"], "Medication adherence and implementation")
        self.assertEqual(a["source_native_id"], "WOS:000001")
        self.assertEqual(a["authors_raw"], ["Lee, A", "Chen, B"])
        self.assertEqual(a["doi"], "10.1234/test-1")
        self.assertEqual(a["pmid"], "12345")
        self.assertEqual(b["raw_record_ordinal"], 2)
        self.assertEqual(a["access_class"], "restricted-license")
        self.assertFalse(a["publication_authorized"])

    def test_reject_incomplete_and_duplicate_export(self):
        with self.assertRaises(SourceFormatError):
            parse_wos_tagged_export(SAMPLE.replace(b"EF\n", b""))
        with self.assertRaises(SourceFormatError):
            parse_wos_tagged_export(SAMPLE.replace(b"WOS:000002", b"WOS:000001"))
        with self.assertRaises(SourceFormatError):
            parse_wos_tagged_export(SAMPLE.replace(b"UT WOS:000002\n", b""))
        with self.assertRaises(SourceFormatError):
            parse_wos_tagged_export(SAMPLE.replace(b"PM 12345", b"PM invalid"))

    def test_doi_validation_does_not_invent_identity(self):
        self.assertEqual(normalize_doi("https://doi.org/10.1234/ABC"), "10.1234/abc")
        self.assertIsNone(normalize_doi("unknown"))
        self.assertIsNone(normalize_doi(None))

    def test_exact_cross_source_merge_and_citation_linkage(self):
        wos = parse_wos_tagged_export(SAMPLE)["records"]
        apa = synthetic("apa_psycinfo", "P001", doi="10.1234/test-1", pmid="12345")
        view = reconcile_sources([*wos, apa])
        self.assertEqual(view["canonical_article_count"], 2)
        merged = next(a for a in view["articles"] if len(a["source_ids"]) == 2)
        self.assertEqual(merged["source_ids"], ["apa_psycinfo", "woscc"])
        self.assertEqual(view["citation_links"][0]["resolution_method"], "exact_doi")
        self.assertEqual(view["citation_links"][0]["cited_article_id"],
                         next(a["canonical_article_id"] for a in view["articles"]
                              if a["doi"] == "10.5678/reference"))
        self.assertFalse(view["public_promotion"])

    def test_conflicting_pmid_blocks_doi_merge(self):
        wos = parse_wos_tagged_export(SAMPLE)["records"][0]
        apa = synthetic("apa_psycinfo", "P001", doi="10.1234/test-1", pmid="99999")
        view = reconcile_sources([wos, apa])
        self.assertEqual(view["canonical_article_count"], 2)
        self.assertEqual(len(view["blocked_identity_pairs"]), 1)

    def test_no_title_fuzzy_or_missing_reference_as_uncited(self):
        a = synthetic("woscc", "WOS:a", refs=["REF NO DOI"])
        b = synthetic("apa_psycinfo", "apa:b")
        view = reconcile_sources([a, b])
        self.assertEqual(view["canonical_article_count"], 2)
        self.assertEqual(view["unresolved_citation_count"], 1)
        self.assertIsNone(view["citation_links"][0]["cited_article_id"])

    def test_leave_one_source_out_recomputes_deterministically(self):
        records = parse_wos_tagged_export(SAMPLE)["records"]
        records.append(synthetic("apa_psycinfo", "P001", doi="10.1234/test-1"))
        a = leave_one_source_out(records)
        b = leave_one_source_out(list(reversed(records)))
        self.assertEqual(canonical_json(a), canonical_json(b))
        self.assertEqual(a["woscc"]["source_counts"], {"apa_psycinfo": 1})
        self.assertEqual(a["apa_psycinfo"]["source_counts"], {"woscc": 2})

    def test_duplicate_source_id_fail_closed(self):
        rec = synthetic("woscc", "WOS:x", doi="10.1000/x")
        with self.assertRaises(SourceFormatError):
            reconcile_sources([rec, dict(rec)])


if __name__ == "__main__":
    unittest.main()
