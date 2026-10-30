"""Synthetic EBSCO CSV Search History reproducibility/negative tests."""
from __future__ import annotations

import csv
import importlib.util
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "scripts/stage2"
sys.path.insert(0, str(STAGE))
SPEC = importlib.util.spec_from_file_location(
    "apa_search_history_audit", STAGE / "apa_search_history_audit.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
SOURCE = (ROOT / "configs/pubmed/medication-adherence-SELECTED.v1.json").read_bytes()
from apa_psycinfo_search_plan import make_plan
QUERY = make_plan(SOURCE)["primary_single_query"]

HEADER = list(audit.REQUIRED)


def example(*, query=QUERY, expanded=QUERY, count="6878",
            language="English", doc="Journal Article", database="APA PsycInfo",
            mode="Близость", search_id="S8") -> bytes:
    row = {
        "Поиск": search_id,
        "Тип поиска": "Одиночный поиск",
        "Запрос (введенный пользователем)": query,
        "Запрос (развернутый/отображаемый термин)": expanded,
        "Дата выполнения поиска (ISO)": "2026-10-30T20:22:07.000Z",
        "Результаты (количество)": count,
        "Тип документа": doc, "Язык": language,
        "Режим поиска": mode, "Количество баз данных": "1",
        "Базы данных": database, "Интерфейс": "EBSCOhost Research Databases",
    }
    stream = io.StringIO(newline="")
    w = csv.DictWriter(stream, fieldnames=HEADER)
    w.writeheader()
    w.writerow(row)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


class TestHistoryAudit(unittest.TestCase):
    def test_success_and_exact_metadata(self):
        report = audit.audit(example(), SOURCE, expected_count=6878)
        self.assertEqual(report["results"], 6878)
        self.assertEqual(report["query_length"], len(QUERY))
        self.assertTrue(report["query_matches_frozen"])
        self.assertTrue(report["expanded_equals_submitted"])
        self.assertFalse(report["expanders_individually_logged_in_csv"])
        self.assertEqual(report["search_mode"], "Близость")

    def test_silent_term_drop_fails(self):
        q = QUERY.replace('"MPR adherence" OR ', '', 1)
        with self.assertRaisesRegex(audit.SearchHistoryAuditError,
                                    "FROZEN_180_TERM_QUERY_MISMATCH"):
            audit.audit(example(query=q, expanded=q), SOURCE)

    def test_silent_expansion_fails(self):
        with self.assertRaisesRegex(audit.SearchHistoryAuditError,
                                    "EXPANDED_QUERY_DIFFERS"):
            audit.audit(example(expanded=QUERY + ' OR "additional subject"'), SOURCE)

    def test_wrong_database_or_filters_fail(self):
        cases = [
            ({"database": "PsycARTICLES"}, "NOT_APA_ONLY"),
            ({"language": "French"}, "FILTERS_NOT_MATCHED"),
            ({"doc": "Any"}, "FILTERS_NOT_MATCHED"),
            ({"mode": "SmartText"}, "MODE_NOT_PROXIMITY"),
        ]
        for edits, message in cases:
            with self.subTest(edits=edits):
                with self.assertRaisesRegex(audit.SearchHistoryAuditError, message):
                    audit.audit(example(**edits), SOURCE)

    def test_source_count_mismatch_fails(self):
        with self.assertRaisesRegex(audit.SearchHistoryAuditError,
                                    "SEARCH_HISTORY_COUNT_NOT_AS_EXPECTED"):
            audit.audit(example(), SOURCE, expected_count=6873)

    def test_missing_id_and_duplicate_rejected(self):
        with self.assertRaisesRegex(audit.SearchHistoryAuditError,
                                    "SEARCH_ID_NOT_UNIQUE_OR_MISSING"):
            audit.audit(example(search_id="S9"), SOURCE)
        header, row = example().decode("utf-8-sig").splitlines()
        with self.assertRaisesRegex(audit.SearchHistoryAuditError,
                                    "SEARCH_ID_NOT_UNIQUE_OR_MISSING"):
            audit.audit(("\ufeff" + header + "\r\n" + row + "\r\n" + row + "\r\n").encode(),
                        SOURCE)

    def test_invalid_encoding_rejected(self):
        with self.assertRaisesRegex(audit.SearchHistoryAuditError, "HISTORY_NOT_UTF8"):
            audit.audit(b"\xff\xfe\x00", SOURCE)


if __name__ == "__main__":
    unittest.main()
