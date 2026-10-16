"""Offline fail-closed PubMed NOT source-translation gate, all synthetic."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pro_adherence import pubmed_evidence as p


QUERY = '("Medication Adherence"[mh]) NOT ("diet"[tiab])'
TRANSLATION = '("Medication Adherence"[MeSH Terms]) NOT ("diet"[Title/Abstract])'
SPEC = {
    "schema": "pubmed-run-spec/v1",
    "task_id": "TASK-0003",
    "query_artifact": "synthetic-future-not-v1",
    "queries": {"Q0": QUERY},
    "operation": "esearch-pmids",
    "partition_policy": p.PARTITION_POLICY,
    "date_start": "2020-01-01",
    "date_end": "2021-12-31",
    "ncbi_config_refs": ["NCBI_TOOL", "NCBI_EMAIL", "NCBI_API_KEY(optional)"],
    "translation_guard": p.NOT_TRANSLATION_GUARD,
}


def response(count, ids, translated=TRANSLATION, warnings=None):
    return p.canonical({"esearchresult": {
        "count": str(count), "idlist": ids,
        "querytranslation": translated,
        "warninglist": {} if warnings is None else warnings,
    }})


class FakeClient:
    def __init__(self, sequence):
        self.sequence = iter(sequence)
        self.sent = []

    def esearch(self, term, retmax):
        self.sent.append((term, retmax))
        return next(self.sequence), {"endpoint": p.ENDPOINT, "method": "POST",
                                     "utc": "2026-10-16T08:00:00Z", "retmax": retmax}


class NotTranslationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        patch = mock.patch.dict(os.environ, {
            "PUBMED_CODE_COMMIT": "a"*40, "PUBMED_RUNTIME": "python-3.13.16",
            "NCBI_TOOL": "offline", "NCBI_EMAIL": "offline@example.org",
        })
        patch.start()
        self.addCleanup(patch.stop)

    def _run(self, replies, *, spec=None):
        target = self.dir / "private-local-only"
        client = FakeClient(replies)
        p.collect(copy.deepcopy(spec or SPEC), "r-"+"b"*32, target, client,
                  timestamp="2026-10-16T08:00:00Z")
        return target, client

    def test_not_count_ignores_quoted_word_and_case(self):
        self.assertEqual(p._not_operator_count('"not"[tiab] AND ("taking"[tiab])'), 0)
        self.assertEqual(p._not_operator_count(QUERY), 1)
        self.assertEqual(p._not_operator_count('A[tiab] NOT B[tiab] NOT C[tiab]'), 2)

    def test_full_mode_rejects_unpinned_guard_before_network(self):
        old = copy.deepcopy(SPEC)
        old.pop("translation_guard")
        with self.assertRaisesRegex(ValueError, "NOT requires"):
            p.check_not_guard_spec(old)
        with self.assertRaisesRegex(ValueError, "NOT requires"):
            self._run([], spec=old)
        self.assertFalse((self.dir / "private-local-only").exists())

    def test_historical_and_not_fails_preflight_without_silent_rewrite(self):
        old = copy.deepcopy(SPEC)
        old["queries"]["Q0"] = QUERY.replace(" NOT ", " AND NOT ")
        with self.assertRaisesRegex(ValueError, "AND NOT"):
            p.check_not_guard_spec(old)
        with self.assertRaisesRegex(ValueError, "AND NOT"):
            self._run([], spec=old)
        self.assertFalse((self.dir / "private-local-only").exists())

    def test_read_spec_pins_policy_without_rewriting_query(self):
        path = self.dir / "spec.json"
        path.write_text(json.dumps(SPEC), encoding="utf-8")
        parsed, run = p.read_spec(path, mode="full", code_commit="a"*40,
                                  runtime="python-3.13.16")
        self.assertEqual(parsed["queries"]["Q0"], QUERY)
        self.assertEqual(parsed["translation_guard"], p.NOT_TRANSLATION_GUARD)
        self.assertTrue(run.startswith("r-"))
        malformed = copy.deepcopy(SPEC)
        malformed["queries"]["Q0"] = QUERY.replace(" NOT ", " AND NOT ")
        path.write_text(json.dumps(malformed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "AND NOT"):
            p.read_spec(path, mode="full", code_commit="a"*40, runtime="python-3.13.16")

    def test_legacy_verifier_trace_does_not_retroactively_reject_old_archives(self):
        raw_dir = self.dir
        rel = p.esearch_raw_path("Q0", 1, "count")
        path = p.strict_path(raw_dir, rel)
        path.parent.mkdir(parents=True)
        raw = response(1, [], "A[Title/Abstract] AND B[Title/Abstract]", {"outputmessages": ["NOT"]})
        path.write_bytes(raw)
        entry = {"query_id":"Q0", "query_sha256":p.sha(QUERY.encode()),
                 "exact_query":QUERY, "file":rel, "endpoint":p.ENDPOINT, "method":"POST",
                 "utc":"2026-10-16T08:00:00Z", "retmax":0, "outcome":"accepted",
                 "result_count":1, "result_ids_sha256":p.sha(p.canonical([]))}
        _roles, pending, accepted, terminal = p.esearch_expected_trace(
            "Q0", QUERY, SPEC["date_start"], SPEC["date_end"], [entry], raw_dir)
        self.assertIsNone(terminal)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(pending), 1)
        with self.assertRaisesRegex(ValueError, "raw ESearch source/metadata"):
            p.esearch_expected_trace(
                "Q0", QUERY, SPEC["date_start"], SPEC["date_end"], [entry], raw_dir,
                translation_guard=p.NOT_TRANSLATION_GUARD)

    def test_source_warning_and_dropped_not_are_not_accepted(self):
        lost = response(1, [], "A[Title/Abstract] AND B[Title/Abstract]", {"outputmessages": ["NOT"]})
        with self.assertRaisesRegex(ValueError, "PubMed NOT"):
            p.check_not_translation(QUERY, p.parse_result(lost))
        with self.assertRaises(ValueError):
            self._run([lost])
        target = self.dir / "private-local-only"
        manifest = json.loads((target / "manifest.json").read_bytes())
        self.assertEqual(manifest["status"], "incomplete")
        self.assertEqual(manifest["failure"]["reason_code"], "search_pending")
        self.assertEqual(manifest["requests"][0]["outcome"], "rejected")
        self.assertEqual(p.verify(target, require_final=False)["status"], "incomplete")
        self.assertNotIn("Q0", manifest["reconciliation"])
        self.assertEqual(len(list((target/"raw/Q0/esearch").glob("*.json"))), 1)

    def test_absent_warning_still_detects_not_translation_loss(self):
        bad = p.parse_result(response(1, [], "A[Title/Abstract] AND B[Title/Abstract]"))
        with self.assertRaisesRegex(ValueError, "NOT lost"):
            p.check_not_translation(QUERY, bad)

    def test_missing_translation_warning_metadata_fails_closed(self):
        for patch in ({"querytranslation": None}, {"warninglist": None},
                      {"warninglist": {"outputmessages": "NOT"}}):
            item = p.parse_result(response(1, []))
            item.update(patch)
            with self.assertRaises(ValueError):
                p.check_not_translation(QUERY, item)

    def test_successful_full_not_search_and_verified_rebuild(self):
        target, client = self._run([response(1, []), response(1, ["12345"])])
        self.assertEqual(client.sent, [(QUERY, 0), (QUERY, 1)])
        first = p.verify(target, require_final=True)
        self.assertEqual(first["status"], "final")
        self.assertEqual(first["counts"], {"Q0": 1})
        manifest = json.loads((target / "manifest.json").read_bytes())
        self.assertEqual(manifest["translation_guard"], p.NOT_TRANSLATION_GUARD)
        self.assertEqual(manifest["reconciliation"]["Q0"]["querytranslation"], TRANSLATION)

    def test_same_query_translation_lost_in_rehashed_raw_rejected_by_verifier(self):
        target, _ = self._run([response(1, []), response(1, ["12345"])])
        path = target / p.esearch_raw_path("Q0", 1, "count")
        raw = json.loads(path.read_bytes())
        raw["esearchresult"]["querytranslation"] = "A[Title/Abstract] AND B[Title/Abstract]"
        path.write_bytes(p.canonical(raw))
        manifest = json.loads((target / "manifest.json").read_bytes())
        rel = p.esearch_raw_path("Q0", 1, "count")
        manifest["files"][rel] = {"bytes": path.stat().st_size,
                                   "sha256": p.sha(path.read_bytes())}
        manifest.pop("package_root_sha256")
        manifest["package_root_sha256"] = p.sha(p.canonical(manifest))
        (target / "manifest.json").write_bytes(p.canonical(manifest)+b"\n")
        with self.assertRaises(ValueError):
            p.verify(target, require_final=True)

    def test_no_not_query_no_false_positive(self):
        p.check_not_translation('"not"[tiab] AND medication[tiab]',
                                {"querytranslation": "", "warninglist": None})


if __name__ == "__main__":
    unittest.main()
