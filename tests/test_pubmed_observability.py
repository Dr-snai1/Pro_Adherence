"""TASK-0030 offline production collector→verify→writer diagnostics; no network."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from pro_adherence import pubmed_evidence as p

CODE = "a" * 40
RUN = "r-" + "f" * 32
REPO = "Dr-snai1/Pro_Adherence-research-evidence"


def reply(count, ids=(), padding=0, marker="fixture"):
    result = {"esearchresult": {"count": str(count), "idlist": list(ids),
              "querytranslation": marker, "warninglist": {}, "errorlist": {}}}
    if padding:
        result["padding"] = "X" * padding
    return json.dumps(result, separators=(",", ":")).encode()


class OfflineClient:
    def __init__(self, replies):
        self.replies = iter(replies)

    def esearch(self, term, retmax):
        item = next(self.replies)
        if isinstance(item, Exception):
            raise item
        return item, {"endpoint": p.ENDPOINT, "method": "POST",
                      "utc": "2026-10-15T00:00:00Z", "retmax": retmax}

    def efetch(self, ids):
        raise AssertionError("EFetch or network is forbidden in offline tests")


def observed(stderr):
    return [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        env = mock.patch.dict(os.environ, {"PUBMED_CODE_COMMIT": CODE, "PUBMED_RUNTIME": "python-3.13.16",
                         "NCBI_TOOL": "fixture-tool", "NCBI_EMAIL": "fixture@example.invalid"})
        env.start()
        self.addCleanup(env.stop)
        self.spec = {"schema": "pubmed-run-spec/v1", "task_id": "TASK-0004",
                     "query_artifact": "offline-instrument-v1", "queries": {"A": "safe-query"},
                     "operation": "esearch-pmids", "partition_policy": p.PARTITION_POLICY,
                     "date_start": "2026-01-01", "date_end": "2026-01-02",
                     "ncbi_config_refs": ["NCBI_TOOL", "NCBI_EMAIL", "NCBI_API_KEY(optional)"]}

    def collect(self, replies, root=None, spec=None):
        root = root or self.base / "package"
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            try:
                value = p.collect(spec or self.spec, RUN, root, OfflineClient(replies),
                                  timestamp="2026-10-15T00:00:00Z")
            except Exception as exc:
                return root, exc, observed(out.getvalue())
        return root, value, observed(out.getvalue())

    def assert_diag(self, event, category, stage, status="unknown", disposition="unknown", size=None):
        self.assertEqual(set(event), {"failure_category", "failure_stage", "package_bytes",
                                     "package_status", "failure_disposition"})
        self.assertEqual(event, {"failure_category": category, "failure_stage": stage,
                         "package_bytes": size, "package_status": status,
                         "failure_disposition": disposition})
        self.assertIn(category, ("SIZE_CAP","SEARCH_PENDING","RECONCILIATION","INTEGRITY","SPEC","UNKNOWN"))

    @staticmethod
    def size(root):
        return sum(f.stat().st_size for f in root.rglob("*") if f.is_file())

    def full(self):
        root, info, ds = self.collect([reply(1), reply(1, ["1234"])])
        self.assertIsInstance(info, dict)
        self.assertEqual(ds, [])
        self.assertEqual(p.verify(root)["status"], "final")
        return root

    def test_h1_real_collector_and_writer_dual_size_cap(self):
        # Actual collect() writes valid >50 MiB raw ESearch response before final verify.
        path = self.base / "h1"
        root, err, ds = self.collect([reply(1, padding=p.MAX_PACKAGE), reply(1, ["1234"])], root=path)
        self.assertIsInstance(err, ValueError)
        self.assertEqual(len(ds), 1)
        n = self.size(root)
        self.assertGreater(n, p.MAX_PACKAGE)
        self.assert_diag(ds[0], "SIZE_CAP", "collect-final-verify", "final", size=n)
        with mock.patch.object(p, "_run", side_effect=AssertionError("Git access prohibited")):
            out = io.StringIO()
            with contextlib.redirect_stderr(out), self.assertRaises(ValueError):
                p.git_write(root, REPO)
        self.assertEqual(len(observed(out.getvalue())), 1)
        self.assert_diag(observed(out.getvalue())[0], "SIZE_CAP", "writer-preflight", "final", size=n)

    def resize_verified_raw(self, root, target):
        rel = "raw/A/esearch/00001-count.json"
        path = root / rel
        mpath = root / "manifest.json"
        manifest = json.loads(mpath.read_bytes())
        # Extra JSON key is ignored by parse_result but remains real hashed raw evidence.
        prefix = b'{"esearchresult":{"count":"1","idlist":[],"querytranslation":"fixture","warninglist":{},"errorlist":{}},"padding":"'
        tail = b'"}'
        fill = max(0, target - self.size(root))
        for _ in range(12):
            payload = prefix + b"X" * fill + tail
            path.write_bytes(payload)
            manifest["files"][rel] = {"sha256": p.sha(payload), "bytes": len(payload)}
            base = {k:v for k,v in manifest.items() if k != "package_root_sha256"}
            manifest["package_root_sha256"] = p.sha(p.canonical(base))
            mpath.write_bytes(p.canonical(manifest) + b"\n")
            delta = target - self.size(root)
            if delta == 0:
                return
            fill += delta
        self.fail("fixture size did not converge")

    def test_exact_50mib_boundary_and_plus_one(self):
        root = self.full()
        for bound in (p.MAX_PACKAGE - 1, p.MAX_PACKAGE, p.MAX_PACKAGE + 1):
            self.resize_verified_raw(root, bound)
            self.assertEqual(self.size(root), bound)
            if bound <= p.MAX_PACKAGE:
                self.assertEqual(p.verify(root)["bytes"], bound)
            else:
                with self.assertRaises(ValueError):
                    p.verify(root)
                sink = io.StringIO()
                with contextlib.redirect_stderr(sink), self.assertRaises(ValueError):
                    p.git_write(root, REPO)
                self.assert_diag(observed(sink.getvalue())[0], "SIZE_CAP",
                                 "writer-preflight", "final", size=bound)

    def test_h2_search_pending_is_verified_and_locally_persisted(self):
        root, err, ds = self.collect([reply(1), RuntimeError("offline interrupted")])
        self.assertIsInstance(err, RuntimeError)
        check = p.verify(root, require_final=False)
        self.assertEqual(check["status"], "incomplete")
        self.assert_diag(ds[0], "SEARCH_PENDING", "collect-search", "incomplete",
                         "resumable", check["bytes"])
        with self.assertRaises(ValueError):
            p.verify(root, require_final=True)
        bare = self.base / "bare.git"
        subprocess.check_call(["git","init","--bare","--initial-branch=main",str(bare)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with mock.patch.object(p,"validate_repository",return_value=str(bare)):
            commit, rel, saved = p.git_write(root, REPO)
        self.assertEqual(saved["status"],"incomplete")
        self.assertEqual(len(commit),40)
        clone = self.base / "readback"
        subprocess.check_call(["git","clone","--quiet","--branch","main",str(bare),str(clone)])
        self.assertEqual(p.verify(clone / rel, require_final=False)["root_hash"],check["root_hash"])

    def test_h3_source_mismatch_terminal_persistable(self):
        root, err, ds = self.collect([reply(10000),reply(1),reply(1,["1234"]),
                                     reply(1),reply(1,["1234"])])
        self.assertIsInstance(err, ValueError)
        check = p.verify(root, require_final=False)
        self.assertEqual(check["failure_reason_code"],"source_count_mismatch")
        self.assert_diag(ds[0],"RECONCILIATION","collect-search","incomplete","terminal",check["bytes"])

    def test_h3_tampered_manifest_inventory_writer_integrity(self):
        root = self.full()
        (root / "reconciliation.json").write_bytes(b"tampered")
        sink = io.StringIO()
        with mock.patch.object(p, "_run", side_effect=AssertionError("must not access Git")):
            with contextlib.redirect_stderr(sink), self.assertRaises(ValueError):
                p.git_write(root, REPO)
        self.assert_diag(observed(sink.getvalue())[0],"INTEGRITY","writer-preflight")

    def test_h4_invalid_spec_cli_no_client(self):
        bad = dict(self.spec, operation="unsafe-operation")
        filename = self.base / "invalid.json"
        filename.write_text(json.dumps(bad))
        err, stdout = io.StringIO(), io.StringIO()
        with mock.patch.object(p,"Client", side_effect=AssertionError("never instantiate client")):
            with contextlib.redirect_stderr(err),contextlib.redirect_stdout(stdout):
                exit_code = p.main(["collect","--spec",str(filename),"--out",str(self.base),
                                    "--mode","full","--code-commit",CODE,"--runtime","python-3.13.16"])
        self.assertEqual(exit_code,1)
        self.assertEqual(stdout.getvalue(),"")
        self.assert_diag(observed(err.getvalue())[0],"SPEC","collect-read-spec")
        self.assertIn("pubmed-evidence: failed (ValueError)",err.getvalue())

    def test_unknown_valueerror_and_redaction_negatives(self):
        sentinels = ("PRIVATE-QUERY-ALPHA","12345678987654321","token_S3NT1N3LQ9",
                     "fake@example.invalid","https://secret.example.invalid/raw/URI")
        self.spec["queries"]["A"] = sentinels[0]
        def injected(*args, **kwargs):
            raise ValueError(" ".join(sentinels))
        with mock.patch.object(p,"query_path",side_effect=injected):
            root, err, ds = self.collect([reply(1)])
        self.assertIsInstance(err,ValueError)
        self.assert_diag(ds[0],"UNKNOWN","collect-search")
        # Test the actual CLI masked line too; never include sentinel values in assertion messages.
        filename = self.base / "invalid-secret.json"
        bad = dict(self.spec, operation="unauthorized")
        filename.write_text(json.dumps(bad))
        e,o=io.StringIO(),io.StringIO()
        with contextlib.redirect_stderr(e),contextlib.redirect_stdout(o):
            code=p.main(["collect","--spec",str(filename),"--out",str(self.base),
                        "--mode","full","--code-commit",CODE,"--runtime","python-3.13.16"])
        self.assertEqual(code,1)
        output=e.getvalue()+o.getvalue()+json.dumps(ds)
        self.assertFalse(any(v in output for v in sentinels), "redaction negative failed")
        self.assertTrue(set(ds[0])=={"failure_category","failure_stage","package_bytes",
                                     "package_status","failure_disposition"})

    def test_no_package_semantics_modified_by_diagnostics(self):
        root=self.full()
        before = {x.relative_to(root).as_posix():p.sha(x.read_bytes()) for x in root.rglob("*") if x.is_file()}
        self.assertEqual(p.verify(root)["status"],"final")
        after = {x.relative_to(root).as_posix():p.sha(x.read_bytes()) for x in root.rglob("*") if x.is_file()}
        self.assertEqual(before,after)
        self.assertEqual(p.MAX_PACKAGE,52428800)


if __name__ == "__main__":
    unittest.main()
