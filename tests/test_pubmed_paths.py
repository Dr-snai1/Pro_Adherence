"""P2-001: semantic artifact-path injectivity, verifier drift, and private Git resume."""
import copy
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import unittest
from unittest import mock

from pro_adherence import pubmed_evidence as p


BASE = {
    "schema": "pubmed-run-spec/v1", "task_id": "TASK-0004",
    "query_artifact": "frozen-artifact-v1",
    "queries": {"A": "query-a", "A-00000": "query-zero"},
    "operation": "esearch-pmids", "partition_policy": p.PARTITION_POLICY,
    "date_start": "2026-01-01", "date_end": "2026-01-02",
    "ncbi_config_refs": ["NCBI_TOOL", "NCBI_EMAIL", "NCBI_API_KEY(optional)"],
}


def search(count, ids=()):
    return json.dumps({"esearchresult": {
        "count": str(count), "idlist": list(ids), "querytranslation": "fixture",
        "warninglist": {},
    }}).encode()


class Fake:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = []

    def esearch(self, term, retmax):
        self.calls.append((term, retmax))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response, {"endpoint": p.ENDPOINT, "method": "POST",
                          "utc": "2026-10-13T00:00:00Z", "retmax": retmax}

    def efetch(self, ids):
        raise AssertionError("no samples in this fixture")


class NamespaceTests(unittest.TestCase):
    RUN = "r-" + "c" * 32

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        env = mock.patch.dict(os.environ, {
            "PUBMED_CODE_COMMIT": "a" * 40, "PUBMED_RUNTIME": "python-3.13.16",
            "NCBI_TOOL": "fixture", "NCBI_EMAIL": "fixture@example.org",
        })
        env.start()
        self.addCleanup(env.stop)

    def spec(self, second="A-00000"):
        spec = copy.deepcopy(BASE)
        spec["queries"] = {"A": "query-a", second: "query-two"}
        return spec

    def collect_pair(self, second, suffix=""):
        spec = self.spec(second)
        source = self.base / ("package-" + second + suffix)
        spec_file = self.base / ("spec-" + second + ".json")
        spec_file.write_text(json.dumps(spec))
        observed, run_id = p.read_spec(spec_file, mode="full",
                                       code_commit="a" * 40, runtime="python-3.13.16")
        self.assertEqual(observed["queries"], spec["queries"])
        self.assertTrue(run_id.startswith("r-"))
        client = Fake([search(1), search(1, ["11"]),
                       search(1), search(1, ["22"])])
        result = p.collect(spec, self.RUN, source, client, timestamp="2026-10-13T00:00:00Z")
        self.assertEqual(result["counts"], {"A": 1, second: 1})
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(p.verify(source)["status"], "final")
        return source

    @staticmethod
    def rehash(root):
        path = root / "manifest.json"
        manifest = json.loads(path.read_bytes())
        for rel in manifest["files"]:
            data = (root / rel).read_bytes()
            manifest["files"][rel] = {"sha256": p.sha(data), "bytes": len(data)}
        manifest.pop("package_root_sha256")
        manifest["package_root_sha256"] = p.sha(p.canonical(manifest))
        path.write_bytes(p.canonical(manifest) + b"\n")

    def test_pairwise_role_namespace_injectivity(self):
        qids = ("A", "A-00000", "A-00001", "A-12345", "Q", "Q-00000",
                "abc", "abc-12345", "A.B", "A_B", "A-B", "Z" * 128)
        identities = []
        for qid in qids:
            identities.extend([(qid, "query", None, p.query_path(qid)),
                               (qid, "union", None, p.union_path(qid)),
                               (qid, "sample", None, p.sample_path(qid))])
            for index in (0, 1, 2, 12345):
                identities.extend([(qid, "leaf", index, p.leaf_path(qid, index)),
                                   (qid, "count", index, p.esearch_raw_path(qid, index + 1, "count")),
                                   (qid, "ids", index, p.esearch_raw_path(qid, index + 1, "ids")),
                                   (qid, "efetch", index, p.efetch_raw_path(qid, index + 1))])
        names = [ident[-1] for ident in identities]
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertEqual(PurePosixPath(name).as_posix(), name)
            self.assertFalse(set(PurePosixPath(name).parts) & {".", ".."})
            self.assertFalse(name.startswith("/"))
            self.assertTrue(all(len(segment.encode()) <= 255 for segment in name.split("/")))
        self.assertNotEqual(p.leaf_path("A", 0), p.union_path("A-00000"))
        self.assertNotEqual(p.leaf_path("A", 1), p.union_path("A-00001"))
        self.assertNotEqual(p.leaf_path("abc", 12345), p.union_path("abc-12345"))
        for fail in (lambda: p.query_path("../A"), lambda: p.leaf_path("A", -1),
                     lambda: p.esearch_raw_path("A", 0, "ids"),
                     lambda: p.efetch_raw_path("A", 0),
                     lambda: p.esearch_raw_path("A", 1, "unknown")):
            with self.assertRaises(ValueError):
                fail()

    def test_collision_shaped_multi_query_final_and_strict_verify(self):
        for second in ("A-00000", "A-00001", "B"):
            with self.subTest(second=second):
                root = self.collect_pair(second)
                self.assertTrue((root / p.leaf_path("A", 0)).exists())
                self.assertTrue((root / p.union_path(second)).exists())
                self.assertNotEqual(p.leaf_path("A", 0), p.union_path(second))

    def test_collision_shaped_git_checkpoint_resume_and_readback(self):
        spec = self.spec()
        source = self.base / "incomplete"
        first = Fake([search(1), search(1, ["11"]), RuntimeError("network interrupted")])
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            p.collect(spec, self.RUN, source, first, timestamp="2026-10-13T00:00:00Z")
        self.assertEqual(p.verify(source, require_final=False)["status"], "incomplete")
        manifest = json.loads((source / "manifest.json").read_bytes())
        self.assertEqual(manifest["query_states"], {"A": "completed", "A-00000": "failed_checkpointable"})
        self.assertEqual((source / p.leaf_path("A", 0)).read_text(), "11\n")
        self.assertEqual((source / p.union_path("A")).read_text(), "11\n")
        self.assertEqual((source / p.query_path("A-00000")).read_text(), "query-two")
        bare = self.base / "private.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with mock.patch.object(p, "validate_repository", return_value=str(bare)):
            first_sha, _, saved = p.git_write(source, "Dr-snai1/Pro_Adherence-research-evidence")
            destination = self.base / "resumed"
            self.assertEqual(p.prepare_resume("Dr-snai1/Pro_Adherence-research-evidence",
                                               "TASK-0004", self.RUN, destination)["root_hash"],
                             saved["root_hash"])
            again = Fake([search(1), search(1, ["22"])])
            final = p.collect(spec, self.RUN, destination, again, resume=True)
            self.assertEqual(final["counts"], {"A": 1, "A-00000": 1})
            self.assertEqual(len(again.calls), 2)
            second_sha, _, _ = p.git_write(destination, "Dr-snai1/Pro_Adherence-research-evidence")
            self.assertNotEqual(first_sha, second_sha)
            check, copied = p.clone_readback("Dr-snai1/Pro_Adherence-research-evidence",
                                             second_sha, "TASK-0004", self.RUN,
                                             target=self.base / "fresh")
            self.assertEqual(check["root_hash"], final["root_hash"])
            self.assertEqual((copied / p.union_path("A-00000")).read_text(), "22\n")
            back = p.backup("Dr-snai1/Pro_Adherence-research-evidence", second_sha,
                            "TASK-0004", self.RUN, self.base / "local")
            self.assertEqual(back["root_hash"], final["root_hash"])
            with self.assertRaises(FileExistsError):
                p.git_write(destination, "Dr-snai1/Pro_Adherence-research-evidence")

    def test_noncanonical_role_metadata_rejected_even_after_rehash(self):
        for role in ("leaf", "union", "raw", "alias"):
            with self.subTest(role=role):
                root = self.collect_pair("A-00000", suffix="-" + role)
                manifest_file = root / "manifest.json"
                manifest = json.loads(manifest_file.read_bytes())
                if role == "leaf":
                    manifest["partitions"][0]["pmid_file"] = p.union_path("A")
                elif role == "union":
                    manifest["reconciliation"]["A"]["pmid_file"] = p.union_path("A-00000")
                elif role == "raw":
                    manifest["requests"][0]["file"] = p.esearch_raw_path("A-00000", 1, "count")
                else:
                    manifest["partitions"][0]["pmid_file"] = manifest["reconciliation"]["A"]["pmid_file"]
                for rel, payload in (("partitions/plan.json", manifest["partitions"]),
                                     ("reconciliation.json", manifest["reconciliation"]),
                                     ("metadata/requests.json", manifest["requests"])):
                    (root / rel).write_bytes(p.canonical(payload))
                manifest_file.write_bytes(p.canonical(manifest))
                self.rehash(root)
                with self.assertRaisesRegex(ValueError, "role|path|alias|noncanonical"):
                    p.verify(root)

    def test_unsafe_spec_rejected_before_network(self):
        for qid in ("A/B", "../bad", "."):
            spec = self.spec()
            spec["queries"] = {qid: "query-a"}
            filename = self.base / ("unsafe-" + str(len(qid)) + ".json")
            filename.write_text(json.dumps(spec))
            fake = Fake([])
            with self.assertRaises(ValueError):
                valid, rid = p.read_spec(filename, mode="full",
                                         code_commit="a" * 40, runtime="python-3.13.16")
                p.collect(valid, rid, self.base / "unsafe-output", fake)
            self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
