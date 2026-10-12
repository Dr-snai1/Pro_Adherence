"""ADM-001 executable regression: checkpoint state, append-only attempts, raw-to-derived lineage."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from pro_adherence import pubmed_evidence as p


BASE = {
    "schema": "pubmed-run-spec/v1", "task_id": "TASK-0004",
    "query_artifact": "frozen-artifact-v1",
    "queries": {"A": "adherence[tiab]"},
    "operation": "esearch-pmids", "partition_policy": p.PARTITION_POLICY,
    "date_start": "2026-01-01", "date_end": "2026-01-02",
    "ncbi_config_refs": ["NCBI_TOOL", "NCBI_EMAIL", "NCBI_API_KEY(optional)"],
}
SAMPLE = {"size": 2, "sha256_prefix": "frozen|A|"}


def search(count, ids=()):
    return json.dumps({"esearchresult": {
        "count": str(count), "idlist": list(ids), "querytranslation": "frozen",
        "warninglist": {},
    }}).encode()


def xml_for(ids):
    return (b"<PubmedArticleSet>"
            + b"".join(f"<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID></MedlineCitation></PubmedArticle>".encode()
                       for pmid in ids)
            + b"</PubmedArticleSet>")


class Fake:
    def __init__(self, responses=(), sample=None):
        self.responses = list(responses)
        self.sample = sample
        self.searches = []
        self.fetches = []

    def esearch(self, term, retmax):
        self.searches.append((term, retmax))
        if not self.responses:
            raise AssertionError("unexpected ESearch")
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value, {"endpoint": p.ENDPOINT, "method": "POST",
                       "utc": "2026-10-12T00:00:00Z", "retmax": retmax}

    def efetch(self, pmids):
        self.fetches.append(list(pmids))
        if isinstance(self.sample, BaseException):
            raise self.sample
        if self.sample is None:
            raise AssertionError("unexpected EFetch")
        return self.sample, {"endpoint": p.EFETCH_ENDPOINT, "method": "POST",
                             "utc": "2026-10-12T00:00:00Z", "retmax": len(pmids)}


class ADM001Tests(unittest.TestCase):
    RID = "r-" + "f" * 32

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        patcher = mock.patch.dict(os.environ, {
            "PUBMED_CODE_COMMIT": "a" * 40, "PUBMED_RUNTIME": "python-3.13.16",
            "NCBI_TOOL": "offline-fixture", "NCBI_EMAIL": "fixture@example.org",
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def bare(self):
        directory = self.base / "private-evidence.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(directory)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return directory

    def persist(self, path, bare):
        with mock.patch.object(p, "validate_repository", return_value=str(bare)):
            return p.git_write(path, "Dr-snai1/Pro_Adherence-research-evidence")

    def resume(self, bare, dest):
        with mock.patch.object(p, "validate_repository", return_value=str(bare)):
            return p.prepare_resume("Dr-snai1/Pro_Adherence-research-evidence",
                                    "TASK-0004", self.RID, dest)

    @staticmethod
    def spec_sample():
        spec = copy.deepcopy(BASE)
        spec["sample_policy"] = {"A": dict(SAMPLE)}
        return spec

    @staticmethod
    def rehash_manifest(root):
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        for rel in manifest["files"]:
            file = root / rel
            manifest["files"][rel] = {"sha256": p.sha(file.read_bytes()), "bytes": file.stat().st_size}
        manifest.pop("package_root_sha256")
        manifest["package_root_sha256"] = p.sha(p.canonical(manifest))
        manifest_path.write_bytes(p.canonical(manifest) + b"\n")

    def test_failed_xml_attempts_survive_durable_checkpoint_retry_and_final(self):
        malformed = b"<PubmedArticleSet><PubmedArticle>"
        wrong_root = b"<unexpected/>"
        mismatch = xml_for(["1", "3"])
        for label, bad in [("malformed", malformed), ("root", wrong_root), ("pmid", mismatch)]:
            with self.subTest(label=label):
                path = self.base / label
                fake = Fake([search(2), search(2, ["1", "2"])], sample=bad)
                with self.assertRaises(ValueError):
                    p.collect(self.spec_sample(), self.RID, path, fake)
                self.assertEqual((path / "raw/A-sample.xml").read_bytes(), bad)
                manifest = json.loads((path / "manifest.json").read_bytes())
                self.assertEqual(manifest["query_states"]["A"], "failed_checkpointable")
                self.assertEqual(manifest["requests"][-1]["outcome"], "rejected")
                checkpoint = p.verify(path, require_final=False)
                self.assertEqual(checkpoint["status"], "incomplete")
                bare = self.base / f"{label}.git"
                subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                first, _, saved = self.persist(path, bare)
                self.assertEqual(saved["root_hash"], checkpoint["root_hash"])
                prepared = self.base / (label + "-readback")
                self.assertEqual(self.resume(bare, prepared)["root_hash"], checkpoint["root_hash"])
                good = Fake(sample=xml_for(["1", "2"]))
                final = p.collect(self.spec_sample(), self.RID, prepared, good, resume=True)
                self.assertEqual(good.searches, [])  # hash-verified reconciled PMIDs reused
                self.assertEqual(good.fetches, [["1", "2"]])
                self.assertEqual((prepared / "raw/A-sample.xml").read_bytes(), bad)
                self.assertEqual((prepared / "raw/A-sample-00002.xml").read_bytes(), xml_for(["1", "2"]))
                self.assertEqual(final["status"], "final")
                second, _, _ = self.persist(prepared, bare)
                self.assertNotEqual(first, second)
                self.assertEqual(subprocess.check_output(
                    ["git", "--git-dir", str(bare), "rev-list", "--count", "main"], text=True).strip(), "2")
                with mock.patch.object(p, "validate_repository", return_value=str(bare)):
                    result, _ = p.clone_readback("Dr-snai1/Pro_Adherence-research-evidence",
                                                 second, "TASK-0004", self.RID,
                                                 target=self.base / (label + "-final-readback"))
                self.assertEqual(result["root_hash"], final["root_hash"])
                with self.assertRaises(FileExistsError):
                    self.persist(prepared, bare)

    def test_pre_response_efetch_outage_has_no_fabricated_raw_and_resumes(self):
        root = self.base / "outage"
        first_client = Fake([search(2), search(2, ["1", "2"])],
                            sample=RuntimeError("fixture network outage"))
        with self.assertRaisesRegex(RuntimeError, "outage"):
            p.collect(self.spec_sample(), self.RID, root, first_client)
        self.assertFalse((root / "raw/A-sample.xml").exists())
        self.assertEqual(p.verify(root, require_final=False)["status"], "incomplete")
        bare = self.bare()
        self.persist(root, bare)
        prepared = self.base / "outage-fresh"
        self.resume(bare, prepared)
        next_client = Fake(sample=xml_for(["1", "2"]))
        self.assertEqual(p.collect(self.spec_sample(), self.RID, prepared,
                                   next_client, resume=True)["status"], "final")
        self.assertEqual(next_client.searches, [])
        self.assertEqual(len(next_client.fetches), 1)

    def test_multi_query_unstarted_identity_git_resume_and_hash_before_network(self):
        spec = copy.deepcopy(BASE)
        spec["queries"] = {"A": "adherence[tiab]", "B": "persistence[tiab]"}
        root = self.base / "multi"
        first_client = Fake([RuntimeError("fixture early outage")])
        with self.assertRaisesRegex(RuntimeError, "outage"):
            p.collect(spec, self.RID, root, first_client)
        manifest = json.loads((root / "manifest.json").read_bytes())
        self.assertEqual(manifest["query_states"], {
            "A": "failed_checkpointable", "B": "not_started"})
        self.assertEqual((root / "queries/B.txt").read_bytes(), b"persistence[tiab]")
        self.assertEqual(len(first_client.searches), 1)
        self.assertEqual(p.verify(root, require_final=False)["status"], "incomplete")
        bare = self.bare()
        self.persist(root, bare)
        tampered = self.base / "tampered"
        self.resume(bare, tampered)
        (tampered / "queries/B.txt").write_text("changed!")
        silent = Fake()
        with self.assertRaisesRegex(ValueError, "hash"):
            p.collect(spec, self.RID, tampered, silent, resume=True)
        self.assertEqual(silent.searches, [])
        fresh = self.base / "multi-fresh"
        self.resume(bare, fresh)
        client = Fake([search(1), search(1, ["9"]), search(0), search(0)])
        self.assertEqual(p.collect(spec, self.RID, fresh, client, resume=True)["counts"],
                         {"A": 1, "B": 0})
        self.assertEqual(p.verify(fresh)["status"], "final")
        self.persist(fresh, bare)

    def test_completed_query_missing_is_not_an_unstarted_query(self):
        spec = copy.deepcopy(BASE)
        spec["queries"] = {"A": "adherence[tiab]", "B": "persistence[tiab]"}
        root = self.base / "corruption"
        client = Fake([search(1), search(1, ["9"]), RuntimeError("failed B")])
        with self.assertRaises(RuntimeError):
            p.collect(spec, self.RID, root, client)
        self.assertEqual(p.verify(root, require_final=False)["status"], "incomplete")
        self.assertEqual(json.loads((root / "manifest.json").read_bytes())["query_states"]["A"], "completed")
        (root / "pmids/A.txt").unlink()
        with self.assertRaises(ValueError):
            p.verify(root, require_final=False)

    def test_incomplete_state_metadata_self_rehash_cannot_forge_completion(self):
        root = self.base / "states"
        with self.assertRaises(RuntimeError):
            p.collect(BASE, self.RID, root, Fake([RuntimeError("outage")]))
        self.assertEqual(p.verify(root, require_final=False)["status"], "incomplete")
        file = root / "manifest.json"
        manifest = json.loads(file.read_bytes())
        manifest["query_states"]["A"] = "completed"
        manifest.pop("package_root_sha256")
        manifest["package_root_sha256"] = p.sha(p.canonical(manifest))
        file.write_bytes(p.canonical(manifest) + b"\n")
        with self.assertRaisesRegex(ValueError, "state"):
            p.verify(root, require_final=False)

    def test_raw_esearch_tamper_with_rehashed_inventory_root_is_rejected(self):
        root = self.base / "source"
        p.collect(BASE, self.RID, root, Fake([search(2), search(2, ["1", "2"])]))
        raw = root / "raw/A-00002-ids.json"
        obj = json.loads(raw.read_bytes())
        obj["esearchresult"]["idlist"] = ["1", "3"]  # derived leaf/union remain 1, 2
        raw.write_bytes(p.canonical(obj))
        self.rehash_manifest(root)  # hash-only integrity is self-consistent
        with self.assertRaisesRegex(ValueError, "raw ESearch"):
            p.verify(root)

    def test_zero_result_sample_is_final_without_efetch(self):
        root = self.base / "zero"
        client = Fake([search(0), search(0)])
        result = p.collect(self.spec_sample(), self.RID, root, client)
        self.assertEqual(result["status"], "final")
        self.assertEqual((root / "samples/A.pmids.txt").read_bytes(), b"")
        self.assertFalse(list((root / "raw").glob("*sample*")))
        self.assertEqual(client.fetches, [])
        self.assertEqual(p.verify(root)["counts"], {"A": 0})


if __name__ == "__main__":
    unittest.main()
