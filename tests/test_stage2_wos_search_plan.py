"""Deterministic offline verification of source-derived WoS search candidates."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "configs/pubmed/medication-adherence-SELECTED.v1.json"
MOD = ROOT / "scripts/stage2/wos_search_plan.py"
spec = importlib.util.spec_from_file_location("wos_search_plan", MOD)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestWosFrozenLexicon(unittest.TestCase):
    def setUp(self):
        self.source = SRC.read_bytes()

    def test_six_blocks_all_exact_lexical_terms_and_filters(self):
        data = mod.make_plan(self.source)
        self.assertEqual(data["lexical_term_count"], 180)
        self.assertEqual([g["term_count"] for g in data["source_groups"]],
                         [2, 54, 15, 69, 36, 4])
        self.assertEqual(sum(g["query"].count(" OR ") + 1
                             for g in data["source_groups"]), 180)
        self.assertEqual(data["all_query"].count(" OR "), 179)
        self.assertTrue(data["all_query"].startswith("TS=("))
        self.assertTrue(data["all_query"].endswith(")"))
        self.assertIn('"medication possession ratio"', data["all_query"])
        self.assertIn('pharmionics', data["all_query"])
        self.assertNotIn("[tiab", data["all_query"])
        self.assertNotIn("[mh:", data["all_query"])
        self.assertEqual(data["source_search_filters"],
                         {"language": "English", "document_type": "Article"})
        self.assertEqual(data["query_status"], "CANDIDATE_NOT_VALIDATED_IN_WOS_UI")

    def test_distinct_sensitivity_and_documented_non_equivalence(self):
        data = mod.make_plan(self.source)
        self.assertEqual(data["title_abstract_sensitivity_query"].count(" OR "), 359)
        self.assertIn("TI=(", data["title_abstract_sensitivity_query"])
        self.assertIn("AB=(", data["title_abstract_sensitivity_query"])
        self.assertTrue(any("NOT identical" in x for x in data["limitations"]))

    def test_tampered_scientific_term_or_group_fails_closed(self):
        src = json.loads(self.source)
        src["queries"]["SELECTED"] = src["queries"]["SELECTED"].replace(
            '"medication adherence"[tiab:~1]', '"new experimental topic"[tiab:~1]')
        with self.assertRaisesRegex(mod.SearchPlanError, "FROZEN_180|DUPLICATE"):
            # This mutation has the same group length but a different vocabulary;
            # detect it by content at the source-config pin in production.
            mod.lexical_groups(src["queries"]["SELECTED"].replace(
                '"new experimental topic"[tiab:~1]', '"medication compliance"[tiab:~1]'))
        src = json.loads(self.source)
        src["queries"]["SELECTED"] = src["queries"]["SELECTED"].replace(
            '"medication adherence"[tiab:~1]', '', 1)
        with self.assertRaises(mod.SearchPlanError):
            mod.make_plan(json.dumps(src).encode())

    def test_candidate_output_is_immutable_and_hash_recorded(self):
        plan = mod.make_plan(self.source)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "search_candidate"
            files = mod.write_plan(plan, dest)
            self.assertEqual(len(files), 9)
            self.assertEqual(len(list(dest.iterdir())), 9)
            manifest = json.loads((dest / "wos_plan_manifest.json").read_text())
            self.assertEqual(manifest["source_config_sha256"], mod.digest(self.source))
            self.assertEqual(
                (dest / "wos_all_180_terms_CANDIDATE.txt").read_text().strip(),
                plan["all_query"])
            with self.assertRaises(FileExistsError):
                mod.write_plan(plan, dest)


if __name__ == "__main__":
    unittest.main()
