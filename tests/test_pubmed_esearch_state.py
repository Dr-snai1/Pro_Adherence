"""P2-002: real collect/verify deterministic ESearch trace and self-rehashed forgeries."""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from pro_adherence import pubmed_evidence as p

SPEC = {
    "schema": "pubmed-run-spec/v1", "task_id": "TASK-0004",
    "query_artifact": "frozen-artifact-v1", "queries": {"A": "query-a"},
    "operation": "esearch-pmids", "partition_policy": p.PARTITION_POLICY,
    "date_start": "2026-01-01", "date_end": "2026-01-02",
    "ncbi_config_refs": ["NCBI_TOOL", "NCBI_EMAIL", "NCBI_API_KEY(optional)"],
}


def raw(count, ids=()):
    return json.dumps({"esearchresult": {
        "count": str(count), "idlist": list(ids),
        "querytranslation": "fixture", "warninglist": {},
    }}).encode()


class Fake:
    def __init__(self, responses):
        self.responses = list(responses)
        self.searches = []

    def esearch(self, term, retmax):
        self.searches.append((term, retmax))
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value, {"endpoint": p.ENDPOINT, "method": "POST",
                       "utc": "2026-10-13T00:00:00Z", "retmax": retmax}

    def efetch(self, pmids):
        raise AssertionError("no EFetch in semantic state tests")


class SemanticStateTests(unittest.TestCase):
    RUN = "r-" + "e" * 32

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = mock.patch.dict(os.environ, {
            "PUBMED_CODE_COMMIT": "a" * 40, "PUBMED_RUNTIME": "python-3.13.16",
            "NCBI_TOOL": "fixture", "NCBI_EMAIL": "fixture@example.org",
        })
        env.start()
        self.addCleanup(env.stop)

    def collect(self, responses, spec=None, name="legit"):
        target = self.root / name
        client = Fake(responses)
        p.collect(spec or SPEC, self.RUN, target, client)
        self.assertEqual(p.verify(target)["status"], "final")
        return target, client

    def forge(self, source, name, mutate):
        target = self.root / name
        shutil.copytree(source, target)
        manifest = json.loads((target / "manifest.json").read_bytes())
        mutate(target, manifest)
        (target / "metadata/requests.json").write_bytes(p.canonical(manifest["requests"]))
        manifest["files"] = {
            f.relative_to(target).as_posix(): {
                "sha256": p.sha(f.read_bytes()), "bytes": f.stat().st_size}
            for f in target.rglob("*") if f.is_file() and f.name != "manifest.json"
        }
        manifest.pop("package_root_sha256")
        manifest["package_root_sha256"] = p.sha(p.canonical(manifest))
        (target / "manifest.json").write_bytes(p.canonical(manifest) + b"\n")
        return target

    def zero(self):
        root, client = self.collect([raw(0), raw(0)])
        self.assertEqual(client.searches, [("query-a", 0), ("query-a", 0)])
        return root

    def test_normal_zero_and_full_module_self_rehashed_role_swap(self):
        source = self.zero()
        def swap(root, manifest):
            one = root / "raw/A/esearch/00001-count.json"
            two = root / "raw/A/esearch/00002-ids.json"
            one.rename(root / "raw/A/esearch/00001-ids.json")
            two.rename(root / "raw/A/esearch/00002-count.json")
            for call in manifest["requests"]:
                call["file"] = call["file"].replace("00001-count", "00001-ids").replace(
                    "00002-ids", "00002-count")
        forged = self.forge(source, "role-swap", swap)
        self.assertEqual(len(json.loads((forged / "manifest.json").read_bytes())["files"]),
                         len(json.loads((source / "manifest.json").read_bytes())["files"]))
        with self.assertRaisesRegex(ValueError, "ESearch semantic role/order/state"):
            p.verify(forged)

    def test_missing_and_duplicate_semantic_operations(self):
        source = self.zero()
        def missing(root, m):
            (root / m["requests"][0]["file"]).unlink()
            m["requests"].pop(0)
        def count_twice(root, m):
            call = copy.deepcopy(m["requests"][0])
            call["file"] = "raw/A/esearch/00003-count.json"
            (root / call["file"]).write_bytes((root / m["requests"][0]["file"]).read_bytes())
            m["requests"].append(call)
        def ids_twice(root, m):
            call = copy.deepcopy(m["requests"][1])
            call["file"] = "raw/A/esearch/00003-ids.json"
            (root / call["file"]).write_bytes((root / m["requests"][1]["file"]).read_bytes())
            m["requests"].append(call)
        def reordered(root, m):
            m["requests"].reverse()
        for name, change in [("missing", missing), ("count-twice", count_twice),
                             ("ids-twice", ids_twice), ("reordered", reordered)]:
            with self.subTest(name=name):
                mutated = self.forge(source, name, change)
                with self.assertRaises(ValueError):
                    p.verify(mutated)

    def test_wrong_query_id_limit_and_suffix_are_self_rehash_rejected(self):
        source = self.zero()
        def wrong_query(root, m):
            m["requests"][1]["exact_query"] = "wrong-query"
            m["requests"][1]["query_sha256"] = p.sha(b"wrong-query")
        def redirect_id(root, m):
            call = m["requests"][0]
            old = root / call["file"]
            call["query_id"] = "A-00000"
            call["file"] = "raw/A-00000/esearch/00001-count.json"
            new = root / call["file"]
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
        def wrong_limit(root, m):
            m["requests"][1]["retmax"] = 1
        def wrong_suffix(root, m):
            call = m["requests"][0]
            old = root / call["file"]
            call["file"] = "raw/A/esearch/00001-ids.json"
            old.rename(root / call["file"])
        for name, change in [("wrong-query", wrong_query), ("qid", redirect_id),
                             ("limit", wrong_limit), ("suffix", wrong_suffix)]:
            with self.subTest(name=name):
                mutated = self.forge(source, name, change)
                with self.assertRaises(ValueError):
                    p.verify(mutated)

    def test_normal_nonzero_count_then_ids_and_wrong_retmax(self):
        source, client = self.collect([raw(2), raw(2, ["7", "9"])])
        self.assertEqual(client.searches, [("query-a", 0), ("query-a", 2)])
        mutated = self.forge(source, "wrong-retmax", lambda root, m:
                             m["requests"][1].__setitem__("retmax", 1))
        with self.assertRaisesRegex(ValueError, "ESearch semantic role/order/state"):
            p.verify(mutated)

    def partition(self, nested=False):
        spec = copy.deepcopy(SPEC)
        if nested:
            spec["date_end"] = "2026-01-04"
        left = [str(i) for i in range(1, 5001)]
        right = [str(i) for i in range(5001, 10001)]
        responses = [raw(10000), raw(10000)]
        if nested:
            responses += [raw(10000)]
        responses += [raw(5000), raw(5000, left),
                      raw(5000), raw(5000, right)]
        if nested:
            responses += [raw(0), raw(0)]
        root, client = self.collect(responses, spec, "nested" if nested else "partition")
        return root, client

    def test_partition_count_ids_chronology_and_self_rehashed_swap(self):
        source, client = self.partition()
        self.assertEqual([x[1] for x in client.searches], [0, 0, 0, 5000, 0, 5000])
        def swap(root, m):
            c, i = m["requests"][2:4]
            path_c, path_i = root / c["file"], root / i["file"]
            dest_c = path_c.with_name("00003-ids.json")
            dest_i = path_i.with_name("00004-count.json")
            path_c.rename(dest_c)
            path_i.rename(dest_i)
            c["file"], i["file"] = dest_c.relative_to(root).as_posix(), dest_i.relative_to(root).as_posix()
        mutated = self.forge(source, "partition-swap", swap)
        with self.assertRaisesRegex(ValueError, "ESearch semantic role/order/state"):
            p.verify(mutated)

    def test_nested_partition_frontier_and_forbidden_internal_ids(self):
        source, client = self.partition(nested=True)
        self.assertEqual([x[1] for x in client.searches], [0, 0, 0, 0, 5000, 0, 5000, 0, 0])
        def wrong_internal(root, m):
            call = m["requests"][2]
            old = root / call["file"]
            call["file"] = call["file"].replace("-count.json", "-ids.json")
            old.rename(root / call["file"])
        bad = self.forge(source, "internal-ids", wrong_internal)
        with self.assertRaisesRegex(ValueError, "ESearch semantic role/order/state"):
            p.verify(bad)

    def test_rejected_count_raw_checkpoint_resume_and_pre_network_validation(self):
        target = self.root / "reject-count"
        first = Fake([b"{broken"])
        with self.assertRaises(ValueError):
            p.collect(SPEC, self.RUN, target, first)
        self.assertEqual(p.verify(target, require_final=False)["status"], "incomplete")
        preserved = (target / "raw/A/esearch/00001-count.json").read_bytes()
        good = Fake([raw(0), raw(0)])
        self.assertEqual(p.collect(SPEC, self.RUN, target, good, resume=True)["status"], "final")
        self.assertEqual(good.searches, [("query-a", 0), ("query-a", 0)])
        self.assertEqual((target / "raw/A/esearch/00001-count.json").read_bytes(), preserved)
        self.assertTrue((target / "raw/A/esearch/00002-count.json").exists())
        self.assertTrue((target / "raw/A/esearch/00003-ids.json").exists())

    def test_rejected_ids_raw_checkpoint_resume_and_tampered_prefix(self):
        target = self.root / "reject-ids"
        with self.assertRaises(ValueError):
            p.collect(SPEC, self.RUN, target, Fake([raw(0), raw(1, ["1"])]))
        self.assertEqual(p.verify(target, require_final=False)["status"], "incomplete")
        bad = self.forge(target, "tampered-failure", lambda root, m:
                         m["requests"][1].__setitem__("exact_query", "alien-query"))
        with self.assertRaisesRegex(ValueError, "ESearch semantic role/order/state"):
            p.verify(bad, require_final=False)
        silent = Fake([])
        with self.assertRaises(ValueError):
            p.collect(SPEC, self.RUN, bad, silent, resume=True)
        self.assertEqual(silent.searches, [])
        good = Fake([raw(0)])
        self.assertEqual(p.collect(SPEC, self.RUN, target, good, resume=True)["status"], "final")
        self.assertEqual(good.searches, [("query-a", 0)])
        self.assertTrue((target / "raw/A/esearch/00003-ids.json").exists())

    def test_resume_mid_partition_without_repeating_completed_operations(self):
        spec = copy.deepcopy(SPEC)
        target = self.root / "prefix"
        left = [str(i) for i in range(1, 5001)]
        right = [str(i) for i in range(5001, 10001)]
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            p.collect(spec, self.RUN, target, Fake([raw(10000), raw(10000), raw(5000),
                      raw(5000, left), RuntimeError("interrupted")]))
        self.assertEqual(p.verify(target, require_final=False)["status"], "incomplete")
        next_client = Fake([raw(5000), raw(5000, right)])
        self.assertEqual(p.collect(spec, self.RUN, target, next_client, resume=True)["status"], "final")
        self.assertEqual(len(next_client.searches), 2)
        self.assertEqual(len(list((target / "raw/A/esearch").glob("*.json"))), 6)


if __name__ == "__main__":
    unittest.main()
