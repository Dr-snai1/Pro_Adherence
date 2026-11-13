"""Regression: no scientific expansion or silent field changes in APA candidate."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "configs/pubmed/medication-adherence-SELECTED.v1.json"
MOD = ROOT / "scripts/stage2/apa_psycinfo_search_plan.py"
sys.path.insert(0, str(MOD.parent))
spec = importlib.util.spec_from_file_location("apa_psycinfo_search_plan", MOD)
apa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apa)


class TestApaCandidate(unittest.TestCase):
    def setUp(self):
        self.source = SRC.read_bytes()
        self.plan = apa.make_plan(self.source)

    def test_180_terms_six_blocks_same_frozen_lexical_source(self):
        p = self.plan
        self.assertEqual(p["terms"], 180)
        self.assertEqual([x["term_count"] for x in p["blocks"]],
                         [2, 54, 15, 69, 36, 4])
        self.assertEqual(p["primary_fields"], ["TI", "AB"])
        self.assertEqual(p["sensitivity_fields"], ["TI", "AB", "KW"])
        self.assertEqual(p["status"],
                         "SOURCE_DERIVED_CANDIDATE_NOT_RUN_IN_LICENSED_EBSCO")
        self.assertEqual(p["primary_single_query"].count(" OR "), 359)
        self.assertEqual(p["keyword_sensitivity_single_query"].count(" OR "), 539)
        self.assertIn('"proportion of days covered"', p["primary_single_query"])
        self.assertIn("pharmionics", p["primary_single_query"])
        self.assertNotIn("KW (", p["primary_single_query"])
        self.assertNotIn("SU (", p["primary_single_query"])
        self.assertNotIn("TI=", p["primary_single_query"])
        self.assertNotIn("[mh", p["primary_single_query"])
        self.assertNotIn("[tiab", p["primary_single_query"])

    def test_each_block_fields_preserve_the_same_terms(self):
        from wos_search_plan import lexical_groups
        original = json.loads(self.source)["queries"]["SELECTED"]
        for group, block in zip(lexical_groups(original), self.plan["blocks"]):
            q = block["primary_query"]
            for term in group:
                needle = f'"{term}"' if " " in term else term
                self.assertEqual(q.count(needle), 2, needle)
            self.assertEqual(q.count(" OR "), 2 * len(group) - 1)
            self.assertEqual(block["keyword_sensitivity_query"].count(" OR "),
                             3 * len(group) - 1)

    def test_citations_do_not_become_source_terms(self):
        self.assertNotIn("APA Thesaurus", self.plan["primary_single_query"])
        self.assertTrue(any("MeSH" in x for x in
                            self.plan["methodological_cautions"]))
        self.assertEqual(self.plan["filters_not_automatically_applied"]["language"],
                         "English")

    def test_no_overwrite_and_manifest_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "candidate"
            files = apa.write_plan(self.plan, target)
            self.assertEqual(len(files), 15)
            m = json.loads((target / "apa_candidate_manifest.json").read_text())
            self.assertEqual(m["source_config_sha256"],
                             self.plan["source_config_sha256"])
            self.assertEqual(
                (target / "apa_PRIMARY_all_180_TI_AB_CANDIDATE.txt").read_text().strip(),
                self.plan["primary_single_query"])
            self.assertEqual(len(list(target.iterdir())), 15)
            with self.assertRaises(FileExistsError):
                apa.write_plan(self.plan, target)

    def test_tampered_frozen_lexicon_fails_closed(self):
        p = json.loads(self.source)
        p["queries"]["SELECTED"] = p["queries"]["SELECTED"].replace(
            '"medication adherence"[tiab:~1]', '', 1)
        with self.assertRaises(apa.SearchPlanError):
            apa.make_plan(json.dumps(p).encode())

    def test_invalid_ebsco_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_EBSCO_FIELD"):
            apa.field_query(["adherence"], "TX")
        with self.assertRaisesRegex(apa.SearchPlanError, "BAD_FIELD_SET"):
            apa.combine_fields(["adherence"], ("TI", "TI"))


if __name__ == "__main__":
    unittest.main()
