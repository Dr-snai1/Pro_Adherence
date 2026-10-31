"""Tests for APA PsycINFO RIS source integrity; all bibliographic data synthetic."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apa_ris_audit", ROOT / "scripts/stage2/apa_ris_audit.py")
apa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apa)


def record(an="2026-00001-001", *, doi="10.1234/synthetic.001",
           db="APA PsycInfo", with_ref=False) -> str:
    data = (f"TY  - JOUR\n"
            f"AB  - First line\n second line\n"
            f"AN  - {an}\n"
            f"ID  - {an}\n"
            f"AU  - Synthetic, Person\n"
            f"DB  - {db}\n"
            f"TI  - A synthetic scientific test record\n"
            f"LA  - eng\n"
            f"JO  - Test Journal\n"
            f"KW  - Medication Adherence\n"
            f"N1  - Journal Article\n"
            f"Y1  - 2026/10/30\n")
    if doi:
        data += f"DO  - {doi}\n"
    if with_ref:
        data += "CR  - Synthetic cited record, 2025\n"
    return data + "ER  - \n"


class TestApaRisAudit(unittest.TestCase):
    def test_counts_integrity_and_missing_references(self):
        raw = (record() + record("2026-00002-001", doi="")).encode()
        result = apa.audit(raw, expected=2)
        self.assertEqual(result["records"], 2)
        self.assertEqual(result["unique_accession_numbers"], 2)
        self.assertEqual(result["with_doi"], 1)
        self.assertEqual(result["with_abstract"], 2)
        self.assertEqual(result["with_article_n1"], 2)
        self.assertEqual(result["with_reference_tags"], 0)
        self.assertEqual(result["with_same_an_and_id"], 2)
        self.assertEqual(result["no_cited_references_claim"],
                         "no_cited_references_exposed_in_RIS")
        self.assertIn("\n second line",
                      apa.parse_ris(raw)[0]["AB"][0])

    def test_missing_records_stop(self):
        with self.assertRaisesRegex(apa.RisAuditError, "RECORD_COUNT_MISMATCH"):
            apa.audit(record().encode(), expected=2)

    def test_duplicate_an_fails_closed(self):
        with self.assertRaisesRegex(apa.RisAuditError, "DUPLICATE_APA_SOURCE_IDS"):
            apa.audit((record()+record()).encode(), expected=2)

    def test_wrong_database_fails_closed(self):
        with self.assertRaisesRegex(apa.RisAuditError, "WRONG_SOURCE_DATABASE"):
            apa.audit(record(db="Some Other Database").encode())

    def test_missing_and_unterminated_records_stop(self):
        with self.assertRaisesRegex(apa.RisAuditError, "UNTERMINATED"):
            apa.audit(record()[:-7].encode())
        with self.assertRaisesRegex(apa.RisAuditError, "NO_RIS_RECORDS"):
            apa.audit(b"\n")

    def test_reference_tags_report_only_if_really_present(self):
        report = apa.audit(record(with_ref=True).encode())
        self.assertEqual(report["with_reference_tags"], 1)
        self.assertEqual(report["no_cited_references_claim"],
                         "some_reference_tags_present_audit_before_use")

    def test_non_utf8_never_silently_replaces_characters(self):
        with self.assertRaisesRegex(apa.RisAuditError, "RIS_ENCODING_NOT_UTF8"):
            apa.audit(b"TY  - JOUR\nAN  - \xff\nER  - \n")

    def test_10_records_have_10_unique_accessions(self):
        raw = "".join(record(f"2026-{i:05d}-001",doi=f"10.0000/test.{i}")
                      for i in range(1,11)).encode()
        report = apa.audit(raw,expected=10)
        self.assertEqual((report["records"],report["unique_accession_numbers"],
                          report["with_doi"],report["with_article_n1"]),
                          (10,10,10,10))


if __name__ == "__main__":
    unittest.main()
