"""Synthetic private-evidence import integration tests. No real PubMed records."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
import importlib.util

from pro_adherence import stage1_private_pilot as pilot

ROOT = Path(__file__).resolve().parents[1]
SOURCE_XML = ROOT / "tests" / "fixtures" / "stage1_pubmed.xml"
HAS_ARROW = importlib.util.find_spec("pyarrow") is not None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def synthetic_package(root):
    pack = Path(root) / "private-synthetic-evidence"
    root_element = ET.fromstring(SOURCE_XML.read_bytes())
    root_element.remove(list(root_element)[-1])  # retain exactly two unique synthetic PMIDs
    raw_xml = ET.tostring(root_element, encoding="utf-8", xml_declaration=True)
    assert raw_xml.count(b"<PubmedArticle>") == 2
    calls, files, hashes, sample_policy = [], {}, {}, {}
    for i, qid in enumerate(pilot.BRANCHES):
        query = f"SYNTHETIC_QUERY_{qid}"
        rels = {
            f"raw/{qid}/efetch/00001.xml": raw_xml,
            f"samples/{qid}/pmids.txt": b"900000001\n900000002\n",
            f"queries/{qid}.txt": query.encode(),
        }
        for rel, raw in rels.items():
            path = pack / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            files[rel] = {"sha256": sha(raw), "bytes": len(raw)}
        hashes[qid] = sha(query.encode())
        sample_policy[qid] = {"size": 2, "sha256_prefix": f"mock|{qid}|"}
        calls.append({"query_id": qid, "file": f"raw/{qid}/efetch/00001.xml",
                      "outcome": "accepted", "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                      "utc": f"2026-10-15T00:39:{i+20:02d}Z"})
    reqs = canonical(calls)
    rel = "metadata/requests.json"
    path = pack / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(reqs)
    files[rel] = {"sha256": sha(reqs), "bytes": len(reqs)}
    manifest = {"files": files, "query_hashes": hashes, "sample_policy": sample_policy,
                "task_id": "TASK-0003", "status": "final", "run_id": "r-"+("a"*32),
                "package_root_sha256": "a"*64}
    (pack / "manifest.json").write_bytes(canonical(manifest))
    return pack


class Stage1PrivateOfflinePilot(unittest.TestCase):
    def test_frozen_query_hash_guard(self):
        m = {"query_hashes": {"x": sha(b"test")}, "run_id": "run"}
        calls = [{"query_id": "x", "file": "raw/x/efetch/00001.xml", "outcome": "accepted",
                  "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                  "utc": "2026-10-15T00:00:00Z"}]
        with self.assertRaisesRegex(ValueError, "query hash mismatch"):
            pilot._source_meta(m, calls, "x", "changed", "b"*40)
        good = pilot._source_meta(m, calls, "x", "test", "b"*40)
        self.assertEqual(good["access_class"], "project-internal")
        self.assertIn("frozen-efetch-sample:", good["source_cursor"])

    def test_deny_workspace_inside_public_source(self):
        with tempfile.TemporaryDirectory() as root:
            pack = synthetic_package(root)
            with self.assertRaisesRegex(ValueError, "independent"):
                pilot.run(pack, ROOT / "research-not-allowed",
                          evidence_commit="b"*40, expected_package_root="a"*64)

    @unittest.skipUnless(HAS_ARROW, "requires dedicated pinned research Parquet CI runtime")
    def test_three_samples_are_diagnostic_private_and_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            pack = synthetic_package(root)
            target = Path(root) / "research"
            with patch.object(pilot.evidence, "verify", return_value={"status": "final"}) as verify:
                r1 = pilot.run(pack, target, evidence_commit="b"*40, expected_package_root="a"*64)
                r2 = pilot.run(pack, target, evidence_commit="b"*40, expected_package_root="a"*64)
            self.assertEqual(r1, r2)
            self.assertEqual((r1["positions"], r1["unique_pmids_across_samples"], r1["overlap_positions"]), (6, 2, 4))
            self.assertEqual(r1["scope"], "FROZEN_SAMPLE_ONLY_NOT_FULL_CORPUS")
            self.assertEqual(r1["status"], "diagnostic-not-promoted")
            self.assertEqual(verify.call_count, 2)
            self.assertTrue((target / "diagnostic_pilot_report.json").is_file())
            for branch in pilot.BRANCHES:
                snapshot = target / branch / "snapshots"
                self.assertEqual(len(list(snapshot.iterdir())), 1)

    @unittest.skipUnless(HAS_ARROW, "requires dedicated pinned research Parquet CI runtime")
    def test_source_tamper_blocks_all_outputs(self):
        with tempfile.TemporaryDirectory() as root:
            pack = synthetic_package(root)
            (pack / "samples" / "V01_D_only" / "pmids.txt").write_text("900000001\n")
            target = Path(root) / "private-result"
            with patch.object(pilot.evidence, "verify", return_value={"status": "final"}):
                with self.assertRaisesRegex(ValueError, "bytes/hash mismatch"):
                    pilot.run(pack, target, evidence_commit="b"*40, expected_package_root="a"*64)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
