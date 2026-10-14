"""TASK-0026 offline regression: PubMed print/electronic date-leaf overlap.

Real collector + independent verifier; no network, dispatch, or remote evidence writes.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from pro_adherence import pubmed_evidence as p

OLD_CODE = "06694b07e635949e80a7e2852c4a688b351faccc"
OLD_PRIMARY = "f92ca88769a79e080c700ff81926e9daf1e25593"
OLD_SENSITIVITY = "63c6e3bee11013b77e72f053e832de434972e106"
ORIGINAL = "configs/pubmed/task-0003-scientific.v01-v02.json"
CORRECTED = "configs/pubmed/task-0003-scientific.v01-v02-ptdelta-r1.json"
SENSITIVITY = "configs/pubmed/task-0003-scientific-sensitivity.v01.json"
BASE_SPEC = {
    "schema": "pubmed-run-spec/v1", "task_id": "TASK-0004",
    "query_artifact": "offline-date-overlap-v1", "queries": {"A": "adherence[tiab]"},
    "operation": "esearch-pmids", "partition_policy": p.PARTITION_POLICY,
    "date_start": "2026-01-01", "date_end": "2026-01-02",
    "ncbi_config_refs": ["NCBI_TOOL", "NCBI_EMAIL", "NCBI_API_KEY(optional)"],
}


def esearch(count, ids=()):
    return json.dumps({"esearchresult": {
        "count": str(count), "idlist": list(ids), "querytranslation": "offline-test",
        "warninglist": {}, "errorlist": {},
    }}).encode()


class OfflineClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def esearch(self, query, retmax):
        self.calls.append((query, retmax))
        return next(self.replies), {
            "endpoint": p.ENDPOINT, "method": "POST",
            "utc": "2026-10-15T00:00:00Z", "retmax": retmax,
        }

    def efetch(self, pmids):
        raise AssertionError("No EFetch/network is allowed in this fixture")


def responses(first, second, base_count=10000):
    # Root count, full-span count, then each non-overlapping date COUNT + IDs.
    return [esearch(base_count), esearch(base_count),
            esearch(len(first)), esearch(len(first), first),
            esearch(len(second)), esearch(len(second), second)]


def rehash_all(root, manifest):
    (root / "reconciliation.json").write_bytes(p.canonical(manifest["reconciliation"]))
    (root / "partitions/plan.json").write_bytes(p.canonical(manifest["partitions"]))
    (root / "metadata/requests.json").write_bytes(p.canonical(manifest["requests"]))
    manifest["files"] = {
        f.relative_to(root).as_posix():
        {"sha256": p.sha(f.read_bytes()), "bytes": f.stat().st_size}
        for f in root.rglob("*") if f.is_file() and f.name != "manifest.json"
    }
    manifest.pop("package_root_sha256", None)
    manifest["package_root_sha256"] = p.sha(p.canonical(manifest))
    (root / "manifest.json").write_bytes(p.canonical(manifest) + b"\n")


class PubdateOverlapTests(unittest.TestCase):
    RID = "r-" + "2" * 32

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "evidence"
        patch = mock.patch.dict(os.environ, {
            "PUBMED_CODE_COMMIT": "b" * 40, "PUBMED_RUNTIME": "python-3.13.16",
            "NCBI_TOOL": "offline", "NCBI_EMAIL": "offline@example.org",
        })
        patch.start()
        self.addCleanup(patch.stop)

    def collect(self, first, second, *, base_count=10000):
        client = OfflineClient(responses(first, second, base_count))
        result = p.collect(copy.deepcopy(BASE_SPEC), self.RID, self.root, client,
                           timestamp="2026-10-15T00:00:00Z")
        return result, client

    def test_overlapping_leaves_final_and_independent_readback(self):
        first = list(map(str, range(1, 6001)))
        second = list(map(str, range(5001, 10001)))
        result, client = self.collect(first, second)
        self.assertEqual(result["status"], "final")
        self.assertEqual(result["counts"], {"A": 10000})
        self.assertEqual([n for _, n in client.calls], [0, 0, 0, 6000, 0, 5000])
        manifest = json.loads((self.root / "manifest.json").read_bytes())
        summary = manifest["reconciliation"]["A"]
        self.assertEqual(summary["source_count"], 10000)
        self.assertEqual(summary["unique_count"], 10000)
        self.assertEqual(summary["duplicates"], 1000)
        self.assertEqual(json.loads((self.root / "reconciliation.json").read_bytes()),
                         manifest["reconciliation"])
        self.assertEqual(p.verify(self.root)["root_hash"], result["root_hash"])
        self.assertEqual((self.root / p.union_path("A")).read_text().splitlines(),
                         list(map(str, range(1, 10001))))

    def test_overlap_with_wrong_unique_union_is_terminal_count_mismatch(self):
        first = list(map(str, range(1, 6001)))
        second = list(map(str, range(5002, 10000)))  # PMID 10000 absent: 9,999 unique.
        with self.assertRaisesRegex(ValueError, "union / source count mismatch"):
            self.collect(first, second)
        manifest = json.loads((self.root / "manifest.json").read_bytes())
        self.assertEqual(manifest["failure"]["reason_code"], "source_count_mismatch")
        self.assertEqual(manifest["failure"]["disposition"], "terminal")
        self.assertEqual(p.verify(self.root, require_final=False)["failure_reason_code"],
                         "source_count_mismatch")
        self.assertNotIn("A", manifest["reconciliation"])
        self.assertFalse((self.root / p.union_path("A")).exists())

    def test_duplicate_within_single_leaf_fails_closed(self):
        first = list(map(str, range(1, 6000))) + ["1"]  # repeated PMID 1
        second = list(map(str, range(5001, 10001)))
        with self.assertRaisesRegex(ValueError, "ESearch retrieval count mismatch"):
            self.collect(first, second)
        self.assertNotIn("A", json.loads((self.root / "reconciliation.json").read_bytes()))
        # Rejected IDS response must never become a trusted canonical leaf.
        self.assertEqual(p.verify(self.root, require_final=False)["status"], "incomplete")

    def test_disjoint_leaves_still_pass_with_zero_duplicates(self):
        result, _ = self.collect(list(map(str, range(1, 5001))),
                                 list(map(str, range(5001, 10001))))
        self.assertEqual(result["counts"], {"A": 10000})
        self.assertEqual(json.loads((self.root / "reconciliation.json").read_bytes())
                         ["A"]["duplicates"], 0)
        self.assertEqual(p.verify(self.root)["status"], "final")

    def test_forged_overlap_diagnostic_with_rehashed_root_fails(self):
        self.collect(list(map(str, range(1, 6001))),
                     list(map(str, range(5001, 10001))))
        manifest = json.loads((self.root / "manifest.json").read_bytes())
        manifest["reconciliation"]["A"]["duplicates"] = 0
        rehash_all(self.root, manifest)
        with self.assertRaisesRegex(ValueError, "reconciliation"):
            p.verify(self.root)

    def test_forged_deduplicated_union_and_rehashed_root_fails(self):
        self.collect(list(map(str, range(1, 6001))),
                     list(map(str, range(5001, 10001))))
        target = self.root / p.union_path("A")
        target.write_text(target.read_text().replace("5000\n", "4999\n", 1))
        manifest = json.loads((self.root / "manifest.json").read_bytes())
        manifest["reconciliation"]["A"]["union_sha256"] = p.sha(target.read_bytes())
        rehash_all(self.root, manifest)
        with self.assertRaises(ValueError):
            p.verify(self.root)

    def test_forged_raw_ids_even_with_rehashed_manifest_fails(self):
        self.collect(list(map(str, range(1, 6001))),
                     list(map(str, range(5001, 10001))))
        raw = self.root / "raw/A/esearch/00004-ids.json"
        value = json.loads(raw.read_bytes())
        value["esearchresult"]["idlist"][0] = "10001"
        raw.write_bytes(p.canonical(value))
        manifest = json.loads((self.root / "manifest.json").read_bytes())
        for request in manifest["requests"]:
            if request["file"] == "raw/A/esearch/00004-ids.json":
                request["result_ids_sha256"] = p.sha(p.canonical(value["esearchresult"]["idlist"]))
        rehash_all(self.root, manifest)
        with self.assertRaises(ValueError):
            p.verify(self.root)

    def test_wrong_date_plan_even_when_rehashed_fails(self):
        self.collect(list(map(str, range(1, 6001))),
                     list(map(str, range(5001, 10001))))
        manifest = json.loads((self.root / "manifest.json").read_bytes())
        manifest["partitions"][1]["date_start"] = "2026-01-01"
        rehash_all(self.root, manifest)
        with self.assertRaises(ValueError):
            p.verify(self.root)

    def test_legacy_terminal_is_code_commit_scoped_and_nonresumable(self):
        same = ["1"]
        client = OfflineClient(responses(same, same))
        with self.assertRaises(ValueError):
            p.collect(copy.deepcopy(BASE_SPEC), self.RID, self.root, client)
        manifest = json.loads((self.root / "manifest.json").read_bytes())
        self.assertEqual(manifest["failure"]["reason_code"], "source_count_mismatch")
        manifest["failure"]["reason_code"] = "cross_leaf_duplicate"
        rehash_all(self.root, manifest)
        with self.assertRaises(ValueError):
            p.verify(self.root, require_final=False)  # new-code false legacy claim
        manifest["code_commit"] = OLD_CODE
        rehash_all(self.root, manifest)
        self.assertEqual(p.verify(self.root, require_final=False)["failure_reason_code"],
                         "cross_leaf_duplicate")
        with self.assertRaises(ValueError):
            p.verify(self.root)  # still incomplete, never a PASS


class ScientificInputDiffTests(unittest.TestCase):
    def test_only_one_query_changes_and_old_blobs_stay_frozen(self):
        root = Path(__file__).resolve().parents[1]
        before = json.loads((root / ORIGINAL).read_bytes())
        after = json.loads((root / CORRECTED).read_bytes())
        self.assertEqual(set(before), set(after))
        self.assertEqual(len(before["queries"]), 7)
        self.assertEqual(set(before["queries"]), set(after["queries"]))
        self.assertEqual(after["queries"]["V01_PT_delta"],
                         before["queries"]["V01_PT_delta"].replace(
                             ' AND NOT "journal article"[pt]',
                             ' NOT "journal article"[pt]'))
        self.assertTrue(after["queries"]["V01_PT_delta"].endswith(
            ' NOT "journal article"[pt]'))
        self.assertFalse(after["queries"]["V01_PT_delta"].endswith(
            ' AND NOT "journal article"[pt]'))
        for key in before:
            if key != "queries":
                self.assertEqual(before[key], after[key], key)
        for key in before["queries"]:
            if key != "V01_PT_delta":
                self.assertEqual(before["queries"][key], after["queries"][key], key)
        for path, blob in ((ORIGINAL, OLD_PRIMARY), (SENSITIVITY, OLD_SENSITIVITY)):
            actual = subprocess.check_output(["git", "hash-object", path],
                                             cwd=root, text=True).strip()
            self.assertEqual(actual, blob, path)
        # The bounded candidate is committed through multiple contents-API
        # commits; pin the accepted baseline as an ancestor, not HEAD^.
        subprocess.run(["git", "merge-base", "--is-ancestor", OLD_CODE, "HEAD"],
                       cwd=root, check=True)


if __name__ == "__main__":
    unittest.main()
